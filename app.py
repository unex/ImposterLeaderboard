import os
import asyncio

from aiohttp import ClientSession, BasicAuth

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import ReturnDocument, ASCENDING, DESCENDING
from bson.objectid import ObjectId

from secrets import token_urlsafe

from itsdangerous.url_safe import URLSafeSerializer

# DB
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_DB = os.environ.get("DB_DB")

# REDDIT API
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")

# APP
REDIRECT_URI_BASE = os.environ.get("REDIRECT_URI_BASE")

SECRET_KEY = os.environ.get('SECRET_KEY', 'this_should_be_configured')
SERIALIZER = URLSafeSerializer(SECRET_KEY)

BOARDS = ['games_played', 'games_won', 'max_lose_streak', 'max_win_streak', 'user_score']

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

mongo: AsyncIOMotorClient
db: AsyncIOMotorCollection
session: ClientSession

@app.on_event("startup")
async def create_db_client():
    global mongo, db, session
    session = ClientSession()
    # Who needs auth DOcKER IS SuPeR sEcuRe
    mongo = AsyncIOMotorClient(host=DB_HOST, port=int(DB_PORT))
    await mongo.admin.command("ismaster")
    db = mongo[DB_DB]

@app.on_event("shutdown")
async def shutdown_db_client():
    await session.close()
    await mongo.close()

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse("error.html", {"request": request, "session": request.session, "exc": exc}, status_code=exc.status_code)

async def user(request: Request, code: str = None, state: str = None, error: str = None) -> dict:
    if 'id' in request.session:
        user = await db.users.find_one({"_id": ObjectId(SERIALIZER.loads(request.session.get('id')))})
        print(user)
        if user: return user

    if not code:
        state = token_urlsafe()
        request.session['oauth2_state'] = state
        return RedirectResponse(f'https://www.reddit.com/api/v1/authorize?client_id={REDDIT_CLIENT_ID}&response_type=code&state={state}&redirect_uri={REDIRECT_URI_BASE + request.url.path}&duration=permanent&scope=identity')

    # Check for state and for 0 errors
    state = request.session.get('oauth2_state')

    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f'There was an error authenticating with reddit: {error}'
        )

    if request.session.get('oauth2_state') != state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'State mismatch'
        )

    auth = BasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
    header = {'User-agent': 'ImposterLeaderboard, /u/RenegadeAI'}
    payload = {
        'redirect_uri': REDIRECT_URI_BASE + request.url.path,
        'grant_type': 'authorization_code',
        'code': code
    }

    r = await session.post('https://www.reddit.com/api/v1/access_token', headers=header, auth=auth, data=payload)
    reddit_token = await r.json()

    if not reddit_token or not 'access_token' in reddit_token:
        return RedirectResponse(app.url_path_for('logout'))

    token = reddit_token["access_token"]

    header['Authorization'] = f'Bearer {token}'

    r = await session.get('https://oauth.reddit.com/api/v1/me', headers=header)
    redditor = await r.json()

    stats = await get_imposter_stats(token)

    user = await db.users.find_one_and_update(
        {'id': redditor['id']},
        {"$set": {
            'name': redditor['name'],
            'icon_img': redditor['icon_img'],
            'token': reddit_token,
            'games_played':	stats['games_played'],
            'games_won': stats['games_won'],
            'user_score': stats['user_score'],
            'user_score_pretty': stats['user_score_pretty'],
            'max_lose_streak': stats['max_lose_streak'],
            'lose_streak': stats['lose_streak'],
            'max_win_streak': stats['max_win_streak'],
            'win_streak': stats['win_streak'],
        }},
        upsert = True,
        return_document=ReturnDocument.AFTER
    )

    request.session["id"] = SERIALIZER.dumps(str(user['_id']))

    return RedirectResponse(app.url_path_for('root'))


async def get_imposter_stats(token):
    header = {'User-agent': 'ImposterLeaderboard, /u/RenegadeAI', 'Authorization': f'Bearer {token}'}
    r = await session.get('https://gremlins-api.reddit.com/status', headers=header)
    try:
        return await r.json()
    except:
        print(f'Could not retrieve imposter stats: {await r.text()}')

@app.get('/')
async def root(request: Request):
    user = None
    if 'id' in request.session:
        user = await db.users.find_one({"_id": ObjectId(SERIALIZER.loads(request.session.get('id')))})

    print(user)

    win = await db.users.find(sort=[('max_win_streak', DESCENDING)]).to_list(50)
    lose = await db.users.find(sort=[('max_lose_streak', DESCENDING)]).to_list(50)
    return templates.TemplateResponse('leaderboard.html', {'request': request, 'user': user, 'boards': BOARDS, 'win': enumerate(win), 'lose': enumerate(lose)})

@app.get('/login')
async def login(request: Request, user = Depends(user)):
    return user

@app.get('/logout')
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(app.url_path_for('root'))

@app.get('/{board}')
async def single_leaderboard(request: Request, board: str):
    user = None
    if 'id' in request.session:
        user = await db.users.find_one({"_id": ObjectId(SERIALIZER.loads(request.session.get('id')))})

    if board in BOARDS:
        users = await db.users.find(sort=[(board, DESCENDING)]).to_list(50)

        return templates.TemplateResponse('board.html', {'request': request, 'user': user, 'board': board, 'users': enumerate(users)})

    raise StarletteHTTPException(status_code=404)
