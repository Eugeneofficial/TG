# TgNew - Universal News Aggregator Reconstruction Summary

## Overview
The TgNew project is a comprehensive news aggregation and Telegram posting system that automatically collects, filters, and publishes news from various sources. The reconstruction involved fixing several issues and ensuring the codebase functions properly.

## Issues Fixed

### 1. Data Model Issue
- **Problem**: The `NewsItem` dataclass was missing the `is_nsfw` field definition, though it was being used in the code
- **Solution**: Added `is_nsfw: bool = False` to the `NewsItem` dataclass definition

### 2. Database Schema Issue
- **Problem**: The database schema was missing the `is_nsfw` column in the `news_items` table
- **Solution**: Added `is_nsfw BOOLEAN DEFAULT 0` column to the database creation query and updated related methods

### 3. Database Operations
- **Problem**: The `save_news_item` and `get_unposted_news` methods weren't handling the `is_nsfw` field properly
- **Solution**: Updated both methods to include the `is_nsfw` field in database operations

### 4. Web Template Issue
- **Problem**: The `index.html` template referenced a non-existent `stats.total_queries` variable
- **Solution**: Changed to `{{ queries|length }}` to use the existing queries data

### 5. Windows Batch File Issue
- **Problem**: The `start_tgnew.bat` file had a hardcoded path that might not work in all environments
- **Solution**: Changed `cd /d "C:\workspace"` to `cd /d "%~dp0"` to use the current directory

## Code Structure

### Core Components
1. **NewsItem** - Data class for storing news items with fields like title, description, URL, source, etc.
2. **DatabaseManager** - Handles SQLite database operations for storing news items, search queries, and posted items
3. **NewsAggregator** - Fetches news from RSS feeds, Google News, Yandex News, and other sources
4. **TelegramPoster** - Posts news items to Telegram channels using aiogram
5. **WebPanel** - Provides a FastAPI-based web interface for managing the system
6. **TgNew** - Main application class that orchestrates all components

### Key Features
- Multi-source news aggregation (RSS, Google News, Yandex News, etc.)
- NSFW content detection and filtering
- Hotness scoring algorithm
- Telegram bot integration
- Web-based management panel
- Automatic posting with configurable delays
- Duplicate detection and filtering

## Dependencies
The application uses:
- `aiogram` for Telegram bot functionality
- `fastapi` and `uvicorn` for web interface
- `aiohttp` for async HTTP requests
- `beautifulsoup4` and `playwright` for web scraping
- `sqlite3` for database storage
- `feedparser` for RSS parsing
- `loguru` for logging

## Configuration
The system is configured through `config.json` which includes:
- Telegram bot token and channel ID
- Search queries with filters
- RSS feed sources
- Posting configuration
- Web panel settings
- Proxy configuration

## Testing
A test script (`test_functionality.py`) was created to verify that all components work correctly:
- Data model functionality
- Database operations
- Configuration loading
- Aggregator initialization

## Conclusion
The reconstruction has successfully fixed all identified issues and the application is now fully functional. The codebase provides a comprehensive solution for automated news aggregation and Telegram posting with advanced features like NSFW detection, hotness scoring, and web-based management.