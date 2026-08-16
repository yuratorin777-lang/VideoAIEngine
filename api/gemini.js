export const runtime = "nodejs";

import { GoogleGenAI } from "@google/genai";

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({
      status: "ERROR",
      message: "Use POST"
    });
  }

  try {
    const { prompt } = req.body || {};

    if (!prompt) {
      return res.status(400).json({
        status: "ERROR",
        message: "Prompt is required"
      });
    }

    const ai = new GoogleGenAI({
      apiKey: process.env.GEMINI_API_KEY
    });

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt
    });

    return res.status(200).json({
      status: "SUCCESS",
      text: response.text || ""
    });

  } catch (error) {
    console.error("Gemini error:", error);

    return res.status(500).json({
      status: "ERROR",
      message: error.message || "Gemini request failed"
    });
  }
}
