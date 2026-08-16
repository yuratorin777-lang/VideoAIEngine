import { GoogleGenerativeAI } from "@google/generative-ai";
import { GoogleAIFileManager } from "@google/generative-ai/server";
import fs from "fs";
import path from "path";
import os from "os";

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
    // В Vercel req.body уже автоматически распарсен
    let bodyData = req.body;
    if (typeof bodyData === "string") {
      try {
        bodyData = JSON.parse(bodyData);
      } catch (e) {
        // Оставляем как есть, если не JSON string
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
    
    let downloadUrl = videoUrl;
    if (videoUrl.includes("drive.google.com")) {
      const fileId = videoUrl.match(/\/d\/([^\/]+)/)?.[1] || videoUrl.match(/id=([^&]+)/)?.[1];
      if (fileId) {
        downloadUrl = `https://drive.google.com/uc?export=download&id=${fileId}`;
      }
    }

    let response = await fetch(downloadUrl);
    
    if (response.headers.get("content-type")?.includes("text/html")) {
      const htmlText = await response.text();
      const confirmCode = htmlText.match(/confirm=([a-zA-Z0-9_]+)/)?.[1];
      if (confirmCode && videoUrl.includes("drive.google.com")) {
        const fileId = videoUrl.match(/\/d\/([^\/]+)/)?.[1] || videoUrl.match(/id=([^&]+)/)?.[1];
        downloadUrl = `https://drive.google.com/uc?export=download&confirm=${confirmCode}&id=${fileId}`;
        response = await fetch(downloadUrl);
      }
    }

    if (!response.ok) {
      throw new Error(`Failed to download video from URL, HTTP status: ${response.status}`);
    }

    const contentType = response.headers.get("content-type") || "video/quicktime";
    const mimeType = contentType.includes("video") ? contentType.split(";")[0] : "video/quicktime";

    const buffer = await response.arrayBuffer();
    const tempFilePath = path.join(os.tmpdir(), `video_${Date.now()}.mov`);
    fs.writeFileSync(tempFilePath, Buffer.from(buffer));

    console.log("Uploading file to Google File API...");
    let fileState = await fileManager.uploadFile(tempFilePath, {
      mimeType: mimeType,
      displayName: "Uploaded Video",
    });

    if (fs.existsSync(tempFilePath)) {
      fs.unlinkSync(tempFilePath);
    }

    console.log("Waiting for video processing...");
    while (fileState.file.state === "PROCESSING") {
      await new Promise((resolve) => setTimeout(resolve, 5000));
      fileState = { file: await fileManager.getFile(fileState.file.name) };
    }

    if (fileState.file.state === "FAILED") {
      throw new Error("Video processing failed on Google servers.");
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
    return res.status(500).json({ error: error.message });
  }
}