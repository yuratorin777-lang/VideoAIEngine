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
    const { prompt, videoUrl } = req.body;

    if (!videoUrl) {
      return res.status(400).json({ error: "videoUrl parameter is required" });
    }

    const genAI = new GoogleGenerativeAI(apiKey);
    const fileManager = new GoogleAIFileManager(apiKey);
    const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });

    console.log("Processing URL:", videoUrl);
    
    let downloadUrl = videoUrl;
    if (videoUrl.includes("drive.google.com")) {
      const fileId = videoUrl.match(/\/d\/([^\/]+)/)?.[1] || videoUrl.match(/id=([^&]+)/)?.[1];
      if (fileId) {
        downloadUrl = `https://drive.google.com/uc?export=download&confirm=no_antivirus&id=${fileId}`;
      }
    }

    const response = await fetch(downloadUrl);
    if (!response.ok) {
      throw new Error(`Failed to download video from URL, HTTP status: ${response.status}`);
    }

    const buffer = await response.arrayBuffer();
    const tempFilePath = path.join(os.tmpdir(), `video_${Date.now()}.mov`);
    fs.writeFileSync(tempFilePath, Buffer.from(buffer));

    console.log("Uploading file to Google File API...");
    const uploadResult = await fileManager.uploadFile(tempFilePath, {
      mimeType: "video/quicktime",
      displayName: "Uploaded Video",
    });

    if (fs.existsSync(tempFilePath)) {
      fs.unlinkSync(tempFilePath);
    }

    console.log("Generating response from Gemini...");
    const result = await model.generateContent([
      {
        fileData: {
          mimeType: uploadResult.file.mimeType,
          fileUri: uploadResult.file.uri,
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