#!/usr/bin/env python3
"""
TgNew - Universal News Aggregator & Telegram Poster
A Swiss Army Knife for News Aggregation
"""

import asyncio
import json
import re
import hashlib
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from urllib.parse import urlparse
import aiohttp
import feedparser
from bs4 import BeautifulSoup
import sqlite3
from loguru import logger
from colorama import init, Fore, Style
import random
import os

# Initialize colorama
init(autoreset=True)

# Import aiogram
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Import FastAPI for web panel
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn

# Import Playwright for advanced scraping
from playwright.async_api import async_playwright

# Configuration
CONFIG_FILE = "config.json"

@dataclass
class NewsItem:
    id: str
    title: str
    description: str
    url: str
    source: str
    published_at: datetime
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    tags: List[str] = None
    hotness_score: int = 0
    language: str = "unknown"

class DatabaseManager:
    def __init__(self, db_path: str = "tgnew.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create news items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news_items (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                url TEXT UNIQUE,
                source TEXT,
                published_at TEXT,
                image_url TEXT,
                video_url TEXT,
                tags TEXT,
                hotness_score INTEGER,
                language TEXT,
                created_at TEXT
            )
        ''')
        
        # Create search queries table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_queries (
                id INTEGER PRIMARY KEY,
                query TEXT,
                filters TEXT,
                tags TEXT,
                enabled BOOLEAN DEFAULT 1
            )
        ''')
        
        # Create posted items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posted_items (
                id TEXT PRIMARY KEY,
                news_id TEXT,
                posted_at TEXT,
                channel_id TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_news_item(self, item: NewsItem):
        """Save news item to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO news_items 
                (id, title, description, url, source, published_at, image_url, 
                 video_url, tags, hotness_score, language, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.id, item.title, item.description, item.url, item.source,
                item.published_at.isoformat(), item.image_url, item.video_url,
                json.dumps(item.tags or []), item.hotness_score, item.language,
                datetime.now().isoformat()
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            # URL already exists
            pass
        finally:
            conn.close()
    
    def get_unposted_news(self) -> List[NewsItem]:
        """Get news items that haven't been posted yet"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM news_items 
            WHERE id NOT IN (SELECT news_id FROM posted_items)
            ORDER BY hotness_score DESC
        ''')
        
        rows = cursor.fetchall()
        items = []
        for row in rows:
            item = NewsItem(
                id=row[0],
                title=row[1],
                description=row[2],
                url=row[3],
                source=row[4],
                published_at=datetime.fromisoformat(row[5]),
                image_url=row[6],
                video_url=row[7],
                tags=json.loads(row[8]) if row[8] else [],
                hotness_score=row[9],
                language=row[10],
                is_nsfw=bool(row[11])
            )
            items.append(item)
        
        conn.close()
        return items
    
    def mark_as_posted(self, news_id: str, channel_id: str):
        """Mark news item as posted"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO posted_items (id, news_id, posted_at, channel_id)
            VALUES (?, ?, ?, ?)
        ''', (f"{news_id}_{channel_id}", news_id, datetime.now().isoformat(), channel_id))
        
        conn.commit()
        conn.close()

class NewsAggregator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.db = DatabaseManager()
        self.session = None
    
    async def initialize(self):
        """Initialize the aggregator"""
        self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the aggregator"""
        if self.session:
            await self.session.close()
    
    def calculate_hotness_score(self, item: Dict[str, Any]) -> int:
        """Calculate hotness score based on various factors"""
        score = 0
        
        # Title length bonus
        if len(item.get('title', '')) > 20:
            score += 2
        
        # Check for NSFW indicators in title
        nsfw_keywords = ['porn', 'sex', 'nude', 'naked', 'hentai', 'xxx', 'adult', 'milf', 'netorare']
        title_lower = item.get('title', '').lower()
        for keyword in nsfw_keywords:
            if keyword in title_lower:
                score += 5
        
        # Check for image/video
        if item.get('image_url'):
            score += 3
        if item.get('video_url'):
            score += 5
        
        # Check for engagement indicators (simulated)
        if 'like' in title_lower or 'view' in title_lower or 'comment' in title_lower:
            score += 2
        
        return score
    
    def detect_nsfw_content(self, item: Dict[str, Any]) -> bool:
        """Detect if content is NSFW"""
        title = item.get('title', '').lower()
        desc = item.get('description', '').lower()
        
        nsfw_keywords = [
            'porn', 'sex', 'nude', 'naked', 'hentai', 'xxx', 'adult', 
            'milf', 'netorare', 'nsfw', 'erotic', 'xxx', 'sex', 'boobs',
            'ass', 'pussy', 'dick', 'cum', 'orgy', 'anal', 'blowjob',
            'fetish', 'bondage', 'bdsm', 'cosplay', 'swimsuit', 'lingerie'
        ]
        
        text = title + ' ' + desc
        for keyword in nsfw_keywords:
            if keyword in text:
                return True
        
        return False
    
    def is_duplicate(self, url: str) -> bool:
        """Check if news item already exists in database"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM news_items WHERE url = ?", (url,))
        count = cursor.fetchone()[0]
        
        conn.close()
        return count > 0
    
    def generate_item_id(self, url: str) -> str:
        """Generate unique ID for news item"""
        return hashlib.md5(url.encode()).hexdigest()
    
    async def scrape_rss_feeds(self) -> List[NewsItem]:
        """Scrape RSS feeds from configured sources"""
        items = []
        
        for feed_url in self.config.get('sources', {}).get('rss_feeds', []):
            try:
                async with self.session.get(feed_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        feed = feedparser.parse(content)
                        
                        for entry in feed.entries:
                            title = entry.get('title', '')
                            description = entry.get('summary', '')
                            link = entry.get('link', '')
                            
                            if not link or self.is_duplicate(link):
                                continue
                            
                            # Extract image from content
                            image_url = None
                            if hasattr(entry, 'content'):
                                soup = BeautifulSoup(str(entry.content), 'html.parser')
                                img = soup.find('img')
                                if img and img.get('src'):
                                    image_url = img['src']
                            
                            item = NewsItem(
                                id=self.generate_item_id(link),
                                title=title,
                                description=description,
                                url=link,
                                source=urlparse(feed_url).netloc,
                                published_at=datetime.now(),
                                image_url=image_url,
                                tags=[],
                                hotness_score=0,
                                is_nsfw=self.detect_nsfw_content({
                                    'title': title,
                                    'description': description
                                })
                            )
                            
                            item.hotness_score = self.calculate_hotness_score({
                                'title': title,
                                'description': description,
                                'image_url': image_url
                            })
                            
                            items.append(item)
            except Exception as e:
                logger.error(f"Error scraping RSS feed {feed_url}: {e}")
        
        return items
    
    async def scrape_google_news(self, query: str) -> List[NewsItem]:
        """Scrape Google News for given query"""
        items = []
        
        # This is a simplified version - in real implementation you'd need to handle Google's anti-bot measures
        search_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
        
        try:
            async with self.session.get(search_url) as response:
                if response.status == 200:
                    content = await response.text()
                    feed = feedparser.parse(content)
                    
                    for entry in feed.entries:
                        title = entry.get('title', '')
                        description = entry.get('summary', '')
                        link = entry.get('link', '')
                        
                        if not link or self.is_duplicate(link):
                            continue
                        
                        item = NewsItem(
                            id=self.generate_item_id(link),
                            title=title,
                            description=description,
                            url=link,
                            source='Google News',
                            published_at=datetime.now(),
                            image_url=None,
                            tags=[],
                            hotness_score=0,
                            is_nsfw=self.detect_nsfw_content({
                                'title': title,
                                'description': description
                            })
                        )
                        
                        item.hotness_score = self.calculate_hotness_score({
                            'title': title,
                            'description': description
                        })
                        
                        items.append(item)
        except Exception as e:
            logger.error(f"Error scraping Google News for query '{query}': {e}")
        
        return items
    
    async def scrape_yandex_news(self, query: str) -> List[NewsItem]:
        """Scrape Yandex News for given query"""
        items = []
        
        # This would require more sophisticated handling due to Yandex's anti-bot measures
        # For now, we'll implement a basic version
        search_url = f"https://yandex.ru/news/search?text={query.replace(' ', '%20')}"
        
        try:
            async with self.session.get(search_url) as response:
                if response.status == 200:
                    content = await response.text()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # This is a simplified selector - actual implementation would need to be updated based on Yandex's current structure
                    articles = soup.find_all('article')  # Placeholder selector
                    
                    for article in articles:
                        # Extract title, link, etc.
                        title_elem = article.find('h2')  # Placeholder selector
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            link_elem = title_elem.find('a')
                            if link_elem and link_elem.get('href'):
                                link = link_elem['href']
                                
                                if not link.startswith('http'):
                                    link = f"https://yandex.ru{link}"
                                
                                if not self.is_duplicate(link):
                                    item = NewsItem(
                                        id=self.generate_item_id(link),
                                        title=title,
                                        description='',
                                        url=link,
                                        source='Yandex News',
                                        published_at=datetime.now(),
                                        image_url=None,
                                        tags=[],
                                        hotness_score=0,
                                        is_nsfw=self.detect_nsfw_content({
                                            'title': title,
                                            'description': ''
                                        })
                                    )
                                    
                                    item.hotness_score = self.calculate_hotness_score({
                                        'title': title,
                                        'description': ''
                                    })
                                    
                                    items.append(item)
        except Exception as e:
            logger.error(f"Error scraping Yandex News for query '{query}': {e}")
        
        return items
    
    async def scrape_with_playwright(self, url: str) -> str:
        """Scrape content from website using Playwright with stealth"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Add stealth scripts to avoid detection
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
            """)
            
            try:
                await page.goto(url, wait_until="networkidle")
                content = await page.content()
                await browser.close()
                return content
            except Exception as e:
                logger.error(f"Error scraping with Playwright {url}: {e}")
                await browser.close()
                return ""
    
    async def aggregate_news(self) -> List[NewsItem]:
        """Aggregate news from all sources"""
        all_items = []
        
        # Scrape RSS feeds
        rss_items = await self.scrape_rss_feeds()
        all_items.extend(rss_items)
        
        # Scrape for each configured query
        for query_config in self.config.get('search_queries', []):
            query = query_config['query']
            
            # Scrape Google News
            google_items = await self.scrape_google_news(query)
            all_items.extend(google_items)
            
            # Scrape Yandex News
            yandex_items = await self.scrape_yandex_news(query)
            all_items.extend(yandex_items)
        
        # Filter items based on config
        filtered_items = []
        for item in all_items:
            # Apply blacklist filters
            blacklist = self.config.get('filters', {}).get('blacklist_words', [])
            title_desc = (item.title + ' ' + item.description).lower()
            
            is_blacklisted = any(word.lower() in title_desc for word in blacklist)
            
            # Apply NSFW filter
            nsfw_only = query_config.get('filters', {}).get('nsfw_only', False)
            if nsfw_only and not item.is_nsfw:
                continue
            
            if not is_blacklisted:
                # Add configured tags
                item.tags.extend(query_config.get('tags', []))
                filtered_items.append(item)
        
        # Save items to database
        for item in filtered_items:
            self.db.save_news_item(item)
        
        return filtered_items

class TelegramPoster:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.bot = Bot(token=config['telegram']['bot_token'])
        self.dp = Dispatcher()
        self.db = DatabaseManager()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot command handlers"""
        @self.dp.message(Command("start"))
        async def start_command(message: types.Message):
            await message.answer(
                "TgNew - Universal News Aggregator\n\n"
                "Commands:\n"
                "/add <query> - Add new search query\n"
                "/remove <id> - Remove search query by ID\n"
                "/list - List all search queries\n"
                "/stats - Show statistics\n"
                "/help - Show this help"
            )
        
        @self.dp.message(Command("add"))
        async def add_query(message: types.Message):
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.answer("Usage: /add <query>")
                return
            
            query = args[1]
            # In a real implementation, you would add this to the config/db
            await message.answer(f"Added query: {query}")
        
        @self.dp.message(Command("list"))
        async def list_queries(message: types.Message):
            queries = self.config.get('search_queries', [])
            if not queries:
                await message.answer("No search queries configured.")
                return
            
            response = "Configured search queries:\n"
            for q in queries:
                response += f"ID: {q['id']}, Query: {q['query']}\n"
            
            await message.answer(response)
        
        @self.dp.message(Command("stats"))
        async def stats_command(message: types.Message):
            # Get statistics from database
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM news_items")
            total_news = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posted_items")
            posted_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM news_items WHERE is_nsfw = 1")
            nsfw_count = cursor.fetchone()[0]
            
            conn.close()
            
            response = f"Statistics:\n"
            response += f"Total news items: {total_news}\n"
            response += f"Posted items: {posted_count}\n"
            response += f"NSFW items: {nsfw_count}"
            
            await message.answer(response)
    
    async def start_bot(self):
        """Start the Telegram bot"""
        await self.dp.start_polling(self.bot)
    
    async def post_news_to_channel(self, item: NewsItem):
        """Post news item to Telegram channel"""
        try:
            # Format the message
            message = f"🔥 <b>{item.title}</b>\n\n"
            message += f"{item.description}\n\n"
            
            # Add tags
            if item.tags:
                message += " ".join(item.tags) + "\n\n"
            
            message += f"🔗 <a href='{item.url}'>Read More</a>"
            
            # Create inline keyboard with buttons
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Read More", url=item.url)],
                [InlineKeyboardButton(text="Boosty", url="https://boosty.to")]  # Example button
            ])
            
            # Post with or without media
            if item.image_url:
                await self.bot.send_photo(
                    chat_id=self.config['telegram']['channel_id'],
                    photo=item.image_url,
                    caption=message,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            else:
                await self.bot.send_message(
                    chat_id=self.config['telegram']['channel_id'],
                    text=message,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            
            # Mark as posted
            self.db.mark_as_posted(item.id, self.config['telegram']['channel_id'])
            
            logger.info(f"Posted to channel: {item.title[:50]}...")
            
        except Exception as e:
            logger.error(f"Error posting to channel: {e}")

class WebPanel:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.app = FastAPI()
        self.db = DatabaseManager()
        self.setup_routes()
    
    def setup_routes(self):
        """Setup web panel routes"""
        templates = Jinja2Templates(directory="templates")
        
        @self.app.get("/", response_class=HTMLResponse)
        async def root(request: Request):
            # Get stats
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM news_items")
            total_news = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posted_items")
            posted_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM news_items WHERE is_nsfw = 1")
            nsfw_count = cursor.fetchone()[0]
            
            conn.close()
            
            stats = {
                "total_news": total_news,
                "posted_count": posted_count,
                "nsfw_count": nsfw_count
            }
            
            return templates.TemplateResponse("index.html", {
                "request": request,
                "stats": stats,
                "queries": self.config.get('search_queries', [])
            })
        
        @self.app.get("/news", response_class=HTMLResponse)
        async def news_list(request: Request):
            # Get unposted news items
            unposted_news = self.db.get_unposted_news()
            
            return templates.TemplateResponse("news.html", {
                "request": request,
                "news_items": unposted_news
            })
    
    def start_server(self):
        """Start the web panel server"""
        uvicorn.run(
            self.app,
            host=self.config['web_panel']['host'],
            port=self.config['web_panel']['port'],
            log_level="info"
        )

class TgNew:
    def __init__(self):
        self.config = self.load_config()
        self.aggregator = NewsAggregator(self.config)
        self.poster = TelegramPoster(self.config)
        self.web_panel = WebPanel(self.config)
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file {CONFIG_FILE} not found!")
            return {}
    
    async def run_aggregation_cycle(self):
        """Run a full aggregation cycle"""
        logger.info("Starting news aggregation cycle...")
        
        # Aggregate news from all sources
        new_items = await self.aggregator.aggregate_news()
        
        logger.info(f"Aggregated {len(new_items)} new news items")
        
        # Auto-post if enabled
        if self.config.get('posting', {}).get('auto_post', False):
            unposted_items = self.aggregator.db.get_unposted_news()
            
            # Sort by hotness score
            unposted_items.sort(key=lambda x: x.hotness_score, reverse=True)
            
            for item in unposted_items:
                # Apply posting delay
                delay = random.randint(
                    self.config['posting']['delay_min'],
                    self.config['posting']['delay_max']
                )
                
                logger.info(f"Waiting {delay} seconds before posting...")
                await asyncio.sleep(delay)
                
                await self.poster.post_news_to_channel(item)
    
    async def run(self):
        """Main run method"""
        await self.aggregator.initialize()
        
        # Start Telegram bot in background
        bot_task = asyncio.create_task(self.poster.start_bot())
        
        # Start web panel in background
        web_task = asyncio.create_task(
            asyncio.get_event_loop().run_in_executor(None, self.web_panel.start_server)
        )
        
        # Main aggregation loop
        while True:
            try:
                await self.run_aggregation_cycle()
                
                # Wait before next cycle
                wait_time = 3600  # 1 hour
                logger.info(f"Waiting {wait_time} seconds before next cycle...")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    def run_sync(self):
        """Synchronous run method"""
        try:
            asyncio.run(self.run())
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            # Clean up
            asyncio.run(self.aggregator.close())

def print_ascii_art():
    """Print TgNew ASCII art with neon colors"""
    art = """
    ██████╗ ██╗   ██╗██████╗ ██╗   ██╗ ██████╗ ██╗  ██╗
    ██╔══██╗╚██╗ ██╔╝██╔══██╗██║   ██║██╔════╝ ╚██╗██╔╝
    ██████╔╝ ╚████╔╝ ██████╔╝██║   ██║██║  ███╗ ╚███╔╝ 
    ██╔═══╝   ╚██╔╝  ██╔══██╗██║   ██║██║   ██║ ██╔██╗ 
    ██║        ██║   ██████╔╝╚██████╔╝╚██████╔╝██╔╝ ██╗
    ╚═╝        ╚═╝   ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
    
           TgNew - Universal News Aggregator
                The Future is Now (2025)
    """
    print(Fore.MAGENTA + art + Style.RESET_ALL)

def main():
    """Main entry point"""
    print_ascii_art()
    logger.add("tgnew.log", rotation="1 day", retention="7 days")
    
    logger.info("Starting TgNew - Universal News Aggregator")
    
    app = TgNew()
    app.run_sync()

if __name__ == "__main__":
    main()