# VideoAIEngine

MVP system for automated video analysis and content generation.

## Current Goal

Validate the simplest useful pipeline:

Video
> Processing
> Gemini
> Structured Result
> Output

## Principles

- MVP first
- Gemini first where useful
- simple local architecture
- real video testing early
- no premature infrastructure

## Project Structure

00_SYSTEM   — system documentation
01_INPUT    — source videos
02_PROCESSING — media preparation
03_ANALYSIS — analysis
04_LIBRARY  — reusable information
05_RETRIEVER — retrieval
06_COMPOSER — content generation
07_OUTPUT   — final results
08_LOGS     — logs

src/         — Python implementation
