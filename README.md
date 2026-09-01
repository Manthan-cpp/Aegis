# 🛡️ Aegis

<img src="https://img.shields.io/badge/Status-Active-success?style=for-the-badge" alt="Status" /> <img src="https://img.shields.io/badge/Code-TypeScript%20%7C%20Python-blue?style=for-the-badge" alt="Code" /> <img src="https://img.shields.io/badge/Architecture-Zero--Cost%20%7C%20Highly%20Scalable-009688?style=for-the-badge" alt="Architecture" />

> **Aegis is a privacy-first, stealth safety and support companion designed specifically for women facing domestic abuse, intense monitoring, or isolation. It is a zero-cost, undetectable safety toolkit that masquerades entirely as a functional, innocent calculator.**

## 🚨 The Problem

When the world feels unsafe, reaching out for help shouldn't put a woman in more danger. For those facing domestic abuse or strict monitoring, openly searching for assistance or making a visible distress call is often impossible. Aegis solves this by hiding a powerful support ecosystem in plain sight.

## 🛡️ Core Ecosystem Overview

1. 🧮 **Stealth Calculator Disguise**: Opens strictly as a working calculator. Entering a specific PIN (e.g., `2580`) and pressing `=` triggers the real app. Pressing Escape or "Quick Exit" instantly clears session data and reverts to the calculator, protecting the user from sudden intrusion.
2. 🖼️ **Discreet SOS via Steganography**: Users type short keywords. An AI (Groq) expands these into a full distress sentence, fetches an innocent cover image (via Pollinations API), and embeds the hidden message invisibly into the image pixels using a custom pure-Python Least Significant Bit (LSB) steganography engine. 
3. 💬 **AI Companion (Emotional Support)**: An always-available chatbot providing grounding techniques. It actively avoids giving medical or legal advice, instead detecting urgent language to surface real crisis resources (112, 181 helplines). Includes native Web Speech API Text-to-Speech (TTS).
4. ⚖️ **India-Scoped Legal Rights RAG Bot**: A specialized Retrieval-Augmented Generation (RAG) assistant that accurately answers queries about Indian Domestic Violence laws (PWDVA, BNS). It queries local vector embeddings to cite specific acts rather than hallucinating.
5. 🚨 **Responder Dashboard**: A secure portal for trusted contacts or NGOs to upload an SOS cover image, decode the hidden message, and view AI-assigned severity scores.

## 🏗️ Stack & Architecture

* **Frontend UI & Stealth Layer:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, GSAP & Lenis, Clerk (Auth).
* **Backend Server:** FastAPI (Python 3.12).
* **AI / Intelligence:** Groq API (`llama-3.3-70b-versatile`) for ultra-fast inference. Local `sentence-transformers/all-MiniLM-L6-v2` for precise embeddings.
* **Database & Vector Store:** MongoDB Atlas M0 (Free Tier) and SQLite.

## 👥 The Team

* **[Manthan Jaiswal](https://github.com/Manthan-cpp)** — Co-Founder , Leader & Backend Developer
* **[Debjeet Mazumder](https://github.com/KingDev4522)** — Co-Founder, Backend Architect & Backend Co-Developer
* **[Debadrita Baksi](https://github.com/debadritabaksi)** — Frontend Co-Developer & UI/UX Architect
* **[Ankit Gupta](https://github.com/ankitgupta91412-sys)** — Frontend Co-Developer & Design Systems Engineer
