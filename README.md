# TechLearning Quiz Agent

An autonomous content pipeline that generates and publishes coding quiz videos for the TechLearning brand — run via command line, not a hosted service.

## What it does

- Generates coding quiz questions across Python, C++, Java, JavaScript, and SQL (400+ question bank)
- Renders quiz videos with background music (two tracks, alternating playback)
- Uploads directly to YouTube via the YouTube Data API (OAuth across two accounts)
- Triggers a Make.com scenario to cross-post the video to Instagram and Facebook Reels with a pinned comment

## Tech Stack

- Python
- YouTube Data API (OAuth 2.0)
- Make.com (webhook-driven cross-posting)

## How it runs

This is a CLI tool — invoked manually from the terminal to generate and publish a batch of quiz videos. Not a hosted/always-on service.

## Results

45+ videos published to date across YouTube, Instagram, and Facebook.

## Status

Actively used for ongoing TechLearning content production.

---
*Built by [Mustufa Aijaz](https://github.com/Mustufa842) — [TechLearning](#)*
