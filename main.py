from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
import os

app = FastAPI(title="DUO-LINER API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGODB_URI")

client = MongoClient(MONGO_URI)

db = client["duoliner_db"]

@app.get("/")
def home():
    return {
        "empresa": "DUO-LINER",
        "status": "online"
    }

@app.get("/clientes")
def clientes():
    return list(db.clientes.find({}, {"_id": 0}))

@app.post("/clientes")
def crear_cliente(cliente: dict):
    db.clientes.insert_one(cliente)
    return {
        "success": True,
        "mensaje": "Cliente guardado"
    }
