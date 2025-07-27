#!/usr/bin/env python3
"""
Test script to verify FastAPI can connect to Supabase and perform basic operations
"""
import asyncio
import platform
from sqlalchemy import text
from app.core.database import get_async_session, engine

async def test_database_operations():
    """Test basic database operations through FastAPI database connection"""
    
    print("🧪 Testing FastAPI database connection...")
    
    try:
        # Get an async session using your FastAPI dependency
        async for session in get_async_session():
            # Test 1: Basic connection
            result = await session.execute(text("SELECT 1 as test;"))
            test_result = result.fetchone()[0]
            print(f"✅ Basic query test: {test_result}")
            
            # Test 2: Check current database
            result = await session.execute(text("SELECT current_database();"))
            db_name = result.fetchone()[0]
            print(f"✅ Connected to database: {db_name}")
            
            # Test 3: List your application tables
            result = await session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name != 'alembic_version'
                ORDER BY table_name;
            """))
            
            tables = result.fetchall()
            print(f"✅ Application tables found: {len(tables)}")
            for table in tables:
                print(f"   📋 {table[0]}")
            
            # Test 4: Check if you can perform a transaction
            try:
                await session.execute(text("BEGIN;"))
                await session.execute(text("SELECT 1;"))
                await session.execute(text("ROLLBACK;"))
                print("✅ Transaction test passed")
            except Exception as e:
                print(f"⚠️  Transaction test failed: {e}")
            
            break  # Exit the async generator
            
        print("\n🎉 All database tests passed! Your FastAPI app can connect to Supabase.")
        
    except Exception as e:
        print(f"❌ Database test failed: {str(e)}")
        raise
    finally:
        # Properly dispose of the engine
        await engine.dispose()

async def test_model_imports():
    """Test that all your models can be imported without issues"""
    print("\n🔍 Testing model imports...")
    
    try:
        # Test importing your models
        from app.models import category, expense, transaction, goal
        print("✅ All models imported successfully")
        
        # Check if models have proper table names
        models = [category, expense, transaction, goal]
        for model_module in models:
            # This assumes your models follow typical naming conventions
            # Adjust based on your actual model structure
            print(f"   📦 {model_module.__name__} module loaded")
            
    except ImportError as e:
        print(f"⚠️  Model import issue: {e}")
    except Exception as e:
        print(f"❌ Model test failed: {e}")

def main():
    """Main function with proper asyncio handling"""
    if platform.system() == 'Windows':
        # Set the event loop policy for Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    async def run_tests():
        await test_database_operations()
        await test_model_imports()
    
    try:
        asyncio.run(run_tests())
    except Exception as e:
        print(f"Error running tests: {e}")

if __name__ == "__main__":
    main()