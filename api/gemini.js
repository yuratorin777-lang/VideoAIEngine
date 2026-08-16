import { GoogleGenerativeAI } from "@google/generative-ai";
import { GoogleAIFileManager } from "@google/generative-ai/server";
import fs from "fs";
import path from "path";
import os from "os";
import axios from "axios";

export default async function handler(req, res) {
  // Настройка CORS
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
    // Безопасное получение req.body в Vercel
    let bodyData = req.body;
    if (typeof bodyData === "string") {
      try {
        bodyData = JSON.parse(bodyData);
      } catch (e) {
        // Оставляем как есть, если распарсить не удалось
      }
    }

    const { prompt, videoUrl } = bodyData || {};

    if (!videoUrl) {
      return res.status(400).json({ error: "videoUrl parameter is required" });
    }

    const genAI = new GoogleGenerativeAI(apiKey);
    const fileManager = new GoogleAIFileManager(apiKey);
    const model = genAI.getGenerativeModel({ model: "gemini-2.0-flash" });

    console.log("Processing URL:", videoUrl);

    // Преобразуем прямую ссылку Google Drive
    let downloadUrl = videoUrl;
    if (videoUrl.includes("drive.google.com")) {
      const fileId = videoUrl.match(/\/d\/([^\/]+)/)?.[1] || videoUrl.match(/id=([^&]+)/)?.[1];
      if (fileId) {
        downloadUrl = `https://drive.google.com/uc?export=download&id=${fileId}`;
      }
    }

    // Скачиваем файл во временную директорию через Axios Stream
    const tempFilePath = path.join(os.tmpdir(), `video_${Date.now()}.mov`);
    
    let downloadResponse = await axios({
      method: "get",
      url: downloadUrl,
      responseType: "stream",
      validateStatus: (status) => status < 400,
    });

    const writer = fs.createWriteStream(tempFilePath);
    downloadResponse.data.pipe(writer);

    await new Promise((resolve, reject) => {
      writer.on("finish", resolve);
      writer.on("error", reject);
    });

    // Определяем MIME-тип
    const contentType = downloadResponse.headers["content-type"] || "video/quicktime";
    const mimeType = contentType.includes("video") ? contentType.split(";")[0] : "video/quicktime";

    console.log("Uploading file to Google File API...", tempFilePath);
    let fileState = await fileManager.uploadFile(tempFilePath, {
      mimeType: mimeType,
      displayName: "Uploaded Video",
    });

    // Удаляем временный файл
    if (fs.existsSync(tempFilePath)) {
      fs.unlinkSync(tempFilePath);
    }

    // Ожидание обработки видео Google API
    console.log("Waiting for video processing...");
    while (fileState.file.state === "PROCESSING") {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      fileState = { file: await fileManager.getFile(fileState.file.name) };
    }

    if (fileState.file.state === "FAILED") {
      throw new Error("Video processing failed on Google servers.");
    }

    console.log("Generating content with Gemini...");
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