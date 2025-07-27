#!/usr/bin/env python3
"""
Script to verify that tables were created successfully in Supabase
"""
import asyncio
import sys
import platform
from sqlalchemy import text
from app.core.database import engine

async def verify_database():
    """Check tables and migration status in Supabase"""
    
    try:
        async with engine.begin() as conn:
            print("🔗 Connected to Supabase database successfully!")
            
            # Check database version
            result = await conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"📊 PostgreSQL version: {version.split(',')[0]}")
            
            # List all tables in public schema
            print("\n📋 Tables in your database:")
            result = await conn.execute(text("""
                SELECT schemaname, tablename 
                FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY tablename;
            """))
            
            tables = result.fetchall()
            if tables:
                for schema, table in tables:
                    print(f"   ✅ {table}")
            else:
                print("   ⚠️  No tables found in public schema")
            
            # Check alembic version
            print("\n🔄 Migration status:")
            try:
                result = await conn.execute(text("SELECT version_num FROM alembic_version;"))
                version = result.fetchone()
                if version:
                    print(f"   ✅ Current Alembic version: {version[0]}")
                else:
                    print("   ⚠️  No Alembic version found")
            except Exception as e:
                print(f"   ⚠️  Alembic version table not accessible: {str(e)}")
            
            # Check table row counts
            print("\n📊 Table statistics:")
            for schema, table in tables:
                if table != 'alembic_version':
                    try:
                        result = await conn.execute(text(f"SELECT COUNT(*) FROM {table};"))
                        count = result.fetchone()[0]
                        print(f"   📈 {table}: {count} rows")
                    except Exception as e:
                        print(f"   ❌ {table}: Error counting rows - {str(e)}")
        
        print("\n✅ Database verification completed successfully!")
        
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        sys.exit(1)
    finally:
        # Properly dispose of the engine
        await engine.dispose()

def main():
    """Main function with proper asyncio handling"""
    if platform.system() == 'Windows':
        # Set the event loop policy for Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(verify_database())
    except Exception as e:
        print(f"Error running verification: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()