import os
import asyncio

from aiohttp import ClientSession, BasicAuth
from motor.motor_asyncio import AsyncIOMotorClient

# DB
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_DB = os.environ.get("DB_DB")

mongo = AsyncIOMotorClient(host=DB_HOST, port=int(DB_PORT))
db = mongo[DB_DB]

# DB
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_DB = os.environ.get("DB_DB")

# REDDIT API
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")

async def task():
    await mongo.admin.command("ismaster")

    session = ClientSession()

    async for user in db.users.find():
        try:
            auth = BasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
            header = {'User-agent': 'ImposterLeaderboard, /u/RenegadeAI'}
            payload = {'grant_type': 'refresh_token', 'refresh_token': user['token']['refresh_token']}
            r = await session.post('https://www.reddit.com/api/v1/access_token', headers=header, auth=auth, data=payload)
            reddit_token = await r.json()

            header['Authorization'] = f'Bearer {reddit_token["access_token"]}'

            r = await session.get('https://gremlins-api.reddit.com/status', headers=header)
            stats = await r.json()

            user = await db.users.find_one_and_update(
                {'id': user['id']},
                {"$set": {
                    'token.access_token': reddit_token['access_token'],
                    'games_played':	stats['games_played'],
                    'games_won': stats['games_won'],
                    'user_score': stats['user_score'],
                    'user_score_pretty': stats['user_score_pretty'],
                    'max_lose_streak': stats['max_lose_streak'],
                    'lose_streak': stats['lose_streak'],
                    'max_win_streak': stats['max_win_streak'],
                    'win_streak': stats['win_streak'],
                }},
            )

            print(f'Updated /u/{user["name"]}')

        except Exception as e:
            print(f'Error: {e}')

    await session.close()
    mongo.close()

loop = asyncio.get_event_loop()

loop.run_until_complete(task())
