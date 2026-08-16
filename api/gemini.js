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
    return res.status(500).json({ error: "GEMINI_API_KEY is missing on server" });
  }

  try {
    let bodyData = req.body;
    if (typeof bodyData === "string") {
      try {
        bodyData = JSON.parse(bodyData);
      } catch (e) {}
    }

    const { prompt, videoUrl } = bodyData || {};

    if (!videoUrl) {
      return res.status(400).json({ error: "videoUrl parameter is required" });
    }

    const genAI = new GoogleGenerativeAI(apiKey);
    const fileManager = new GoogleAIFileManager(apiKey);
    const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash-latest" });

    console.log("Processing URL:", videoUrl);

    // Извлекаем ID файла из Google Drive
    let fileId = null;
    if (videoUrl.includes("drive.google.com")) {
      fileId = videoUrl.match(/\/d\/([^\/]+)/)?.[1] || videoUrl.match(/id=([^&]+)/)?.[1];
    }

    let downloadUrl = fileId 
      ? `https://drive.google.com/uc?export=download&id=${fileId}` 
      : videoUrl;

    // Инициализируем Axios сессию
    const client = axios.create({
      timeout: 30000,
      maxRedirects: 5,
    });

    let response = await client.get(downloadUrl, { responseType: "arraybuffer" });

    // Проверяем, не вернул ли Google Drive HTML-страницу подтверждения скачивания
    const contentTypeHeader = response.headers["content-type"] || "";
    if (contentTypeHeader.includes("text/html") && fileId) {
      const htmlContent = Buffer.from(response.data).toString("utf8");
      // Ищем токен подтверждения вирусов
      const confirmCode = htmlContent.match(/confirm=([a-zA-Z0-9_]+)/)?.[1] ||
                          htmlContent.match(/name="confirm" value="([^"]+)"/)?.[1];

      if (confirmCode) {
        const confirmUrl = `https://drive.google.com/uc?export=download&confirm=${confirmCode}&id=${fileId}`;
        response = await client.get(confirmUrl, { responseType: "arraybuffer" });
      }
    }

    const videoBuffer = Buffer.from(response.data);

    // Проверяем, что скачан именно бинарный файл, а не HTML с ошибкой
    if (videoBuffer.slice(0, 100).toString("utf8").includes("<!DOCTYPE html>")) {
      throw new Error("Failed to download video file from Google Drive (received HTML instead of video binary). Make sure the file access is set to 'Anyone with the link'.");
    }

    const tempFilePath = path.join(os.tmpdir(), `video_${Date.now()}.mov`);
    fs.writeFileSync(tempFilePath, videoBuffer);

    console.log("Uploading file to Google File API...", tempFilePath);
    let fileState = await fileManager.uploadFile(tempFilePath, {
      mimeType: "video/quicktime",
      displayName: "Uploaded Video",
    });

    if (fs.existsSync(tempFilePath)) {
      fs.unlinkSync(tempFilePath);
    }

    console.log("Waiting for video processing...");
    let attempts = 0;
    while (fileState.file.state === "PROCESSING") {
      if (attempts > 30) { // Ограничение ожидания 2.5 минуты
        throw new Error("Video processing timeout on Google servers.");
      }
      await new Promise((resolve) => setTimeout(resolve, 5000));
      fileState = { file: await fileManager.getFile(fileState.file.name) };
      attempts++;
    }

    if (fileState.file.state === "FAILED") {
      throw new Error("Video processing failed on Google servers. File format or codec may not be supported by Gemini.");
    }

    console.log("Generating response from Gemini...");
    const result = await model.generateContent([
      {
        fileData: {
          mimeType: fileState.file.mimeType,
          fileUri: fileState.file.uri,
        },
      },
      { text: prompt || "Опиши подробно, что происходит на этом видео." },
    ]);

    return res.status(200).json({ text: result.response.text() });

  } catch (error) {
    console.error("Proxy Error:", error);
    return res.status(500).json({ error: error.message || "Internal server error" });
  }
}