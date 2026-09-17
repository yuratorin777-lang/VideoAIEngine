import { GoogleGenerativeAI } from "@google/generative-ai";
import { GoogleAIFileManager } from "@google/generative-ai/server";
import fs from "fs";
import path from "path";
import os from "os";
import axios from "axios";

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const apiKey = process.env.GEMINI_API_KEY;

  if (!apiKey) {
    return res.status(500).json({
      error: "GEMINI_API_KEY is missing on server",
    });
  }

  try {
    let bodyData = req.body;

    if (typeof bodyData === "string") {
      try {
        bodyData = JSON.parse(bodyData);
      } catch (e) {
        return res.status(400).json({
          error: "Invalid JSON body",
        });
      }
    }

    const {
      prompt,
      videoUrl,
      systemInstruction,
      responseMimeType,
      temperature,
      action,
    } = bodyData || {};

    if (!prompt || typeof prompt !== "string") {
      return res.status(400).json({
        error: "prompt parameter is required",
      });
    }

    const genAI = new GoogleGenerativeAI(apiKey);

    /*
     * ============================================================
     * TEXT-ONLY MODE
     * ============================================================
     *
     * Используется Retriever.
     *
     * videoUrl отсутствует → Gemini получает только текстовый
     * prompt + systemInstruction.
     */

    if (!videoUrl) {
      console.log("[Gemini Proxy] TEXT MODE");

      const modelConfig = {
        model: "gemini-3.5-flash-lite",
      };

      if (systemInstruction) {
        modelConfig.systemInstruction = {
          parts: [
            {
              text: systemInstruction,
            },
          ],
        };
      }

      const model = genAI.getGenerativeModel(modelConfig);

      const generationConfig = {
        temperature:
          typeof temperature === "number"
            ? temperature
            : 0.2,
      };

      if (responseMimeType) {
        generationConfig.responseMimeType = responseMimeType;
      }

      const result = await model.generateContent({
        contents: [
          {
            role: "user",
            parts: [
              {
                text: prompt,
              },
            ],
          },
        ],
        generationConfig,
      });

      const text = result.response.text();

      console.log("[Gemini Proxy] TEXT MODE completed");

      return res.status(200).json({
        text,
      });
    }

    /*
     * ============================================================
     * VIDEO MODE
     * ============================================================
     *
     * Существующий режим анализа видео.
     *
     * videoUrl есть → скачиваем видео из Google Drive,
     * загружаем его в Gemini File API и передаем Gemini.
     */

    console.log("[Gemini Proxy] VIDEO MODE");
    console.log("Processing URL:", videoUrl);

    const fileManager = new GoogleAIFileManager(apiKey);

    const model = genAI.getGenerativeModel({
      model: "gemini-3.5-flash-lite",
    });

    // Извлекаем ID файла из Google Drive

    let fileId = null;

    if (videoUrl.includes("drive.google.com")) {
      fileId =
        videoUrl.match(/\/d\/([^\/]+)/)?.[1] ||
        videoUrl.match(/id=([^&]+)/)?.[1];
    }

    const downloadUrl = fileId
      ? `https://drive.google.com/uc?export=download&id=${fileId}`
      : videoUrl;

    // Axios client

    const client = axios.create({
      timeout: 30000,
      maxRedirects: 5,
    });

    let response = await client.get(downloadUrl, {
      responseType: "arraybuffer",
    });

    // Проверяем Google Drive confirmation page

    const contentTypeHeader =
      response.headers["content-type"] || "";

    if (
      contentTypeHeader.includes("text/html") &&
      fileId
    ) {
      const htmlContent = Buffer.from(
        response.data
      ).toString("utf8");

      const confirmCode =
        htmlContent.match(
          /confirm=([a-zA-Z0-9_]+)/
        )?.[1] ||
        htmlContent.match(
          /name="confirm" value="([^"]+)"/
        )?.[1];

      if (confirmCode) {
        const confirmUrl =
          `https://drive.google.com/uc?export=download` +
          `&confirm=${confirmCode}` +
          `&id=${fileId}`;

        response = await client.get(confirmUrl, {
          responseType: "arraybuffer",
        });
      }
    }

    const videoBuffer = Buffer.from(response.data);

    // Проверяем HTML вместо видео

    const firstBytes = videoBuffer
      .slice(0, 500)
      .toString("utf8");

    if (
      firstBytes.includes("<!DOCTYPE html>") ||
      firstBytes.includes("<html")
    ) {
      throw new Error(
        "Failed to download video file from Google Drive. " +
        "Received HTML instead of video binary. " +
        "Make sure the file access is set to 'Anyone with the link'."
      );
    }

    if (videoBuffer.length < 1024) {
      throw new Error(
        `Downloaded video is too small: ${videoBuffer.length} bytes`
      );
    }

    /*
     * Определяем расширение.
     *
     * Для Gemini File API можно использовать временный .mp4.
     * MIME ниже определяем из URL/Google Drive либо используем
     * video/mp4 как безопасный основной вариант.
     */

    let tempExtension = ".mp4";
    let mimeType = "video/mp4";

    if (
      videoUrl.toLowerCase().includes(".mov") ||
      videoUrl.toLowerCase().includes("video/quicktime")
    ) {
      tempExtension = ".mov";
      mimeType = "video/quicktime";
    }

    const tempFilePath = path.join(
      os.tmpdir(),
      `video_${Date.now()}${tempExtension}`
    );

    fs.writeFileSync(
      tempFilePath,
      videoBuffer
    );

    console.log(
      "Uploading file to Google File API...",
      tempFilePath
    );

    let fileState =
      await fileManager.uploadFile(
        tempFilePath,
        {
          mimeType,
          displayName: "Uploaded Video",
        }
      );

    if (fs.existsSync(tempFilePath)) {
      fs.unlinkSync(tempFilePath);
    }

    console.log(
      "Waiting for video processing..."
    );

    let attempts = 0;

    while (
      fileState.file.state === "PROCESSING"
    ) {
      if (attempts > 30) {
        throw new Error(
          "Video processing timeout on Google servers."
        );
      }

      await new Promise((resolve) =>
        setTimeout(resolve, 5000)
      );

      fileState = {
        file: await fileManager.getFile(
          fileState.file.name
        ),
      };

      attempts++;
    }

    if (
      fileState.file.state === "FAILED"
    ) {
      throw new Error(
        "Video processing failed on Google servers. " +
        "File format or codec may not be supported by Gemini."
      );
    }

    console.log(
      "Generating response from Gemini..."
    );

    const result =
      await model.generateContent([
        {
          fileData: {
            mimeType:
              fileState.file.mimeType,
            fileUri:
              fileState.file.uri,
          },
        },
        {
          text:
            prompt ||
            "Опиши подробно, что происходит на этом видео.",
        },
      ]);

    return res.status(200).json({
      text: result.response.text(),
    });
  } catch (error) {
    console.error(
      "[Gemini Proxy] Error:",
      error
    );

    return res.status(500).json({
      error:
        error.message ||
        "Internal server error",
    });
  }
}