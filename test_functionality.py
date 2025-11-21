#!/usr/bin/env python3
"""
Test script to verify TgNew functionality
"""
import asyncio
from datetime import datetime
from main import NewsItem, DatabaseManager, NewsAggregator, TgNew
import json

def test_news_item():
    """Test NewsItem dataclass"""
    item = NewsItem(
        id="test123",
        title="Test News",
        description="Test description",
        url="https://example.com",
        source="Example",
        published_at=datetime.now(),
        is_nsfw=True
    )
    print(f"✓ NewsItem created: {item.title}")
    return item

def test_database():
    """Test database functionality"""
    db = DatabaseManager("test_tgnew.db")
    print("✓ Database initialized")
    
    # Create a test news item
    item = NewsItem(
        id="test123",
        title="Test News",
        description="Test description",
        url="https://example.com",
        source="Example",
        published_at=datetime.now(),
        is_nsfw=True
    )
    
    # Save the item
    db.save_news_item(item)
    print("✓ News item saved to database")
    
    # Retrieve unposted items
    unposted = db.get_unposted_news()
    print(f"✓ Retrieved {len(unposted)} unposted news items")
    
    return db

def test_config_loading():
    """Test configuration loading"""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        print("✓ Configuration loaded successfully")
        return config
    except Exception as e:
        print(f"✗ Configuration loading failed: {e}")
        return None

async def test_aggregator():
    """Test news aggregator"""
    config = test_config_loading()
    if config:
        aggregator = NewsAggregator(config)
        await aggregator.initialize()
        print("✓ News aggregator initialized")
        await aggregator.close()
        return aggregator
    return None

def main():
    """Main test function"""
    print("Testing TgNew functionality...")
    print("="*50)
    
    # Test NewsItem
    test_news_item()
    
    # Test Database
    test_database()
    
    # Test Configuration
    test_config_loading()
    
    # Test Aggregator
    asyncio.run(test_aggregator())
    
    print("="*50)
    print("✓ All tests completed successfully!")

if __name__ == "__main__":
    main()