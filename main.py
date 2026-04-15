from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from sqlalchemy.orm import Session
import models
import database

# Create the tables
models.Base.metadata.create_all(bind=database.engine)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

# Permite que seu Frontend acesse o Backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers para ler/escrever JSON
def read_json(filename):
    if not os.path.exists(filename): return []
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- ROTAS ---

@app.get("/matches")
def get_matches(db: Session = Depends(get_db)):
    matches = db.query(models.Match).all()
    return matches

@app.get("/guesses/{user_id}")
def get_user_guesses(user_id: int, db: Session = Depends(get_db)):
    # Busca todos os palpites onde o campo user_id coincide com o parâmetro da URL
    guesses = db.query(models.Guess).filter(models.Guess.user_id == user_id).all()
    
    # O FastAPI converte automaticamente a lista de objetos do banco para JSON
    return guesses

@app.post("/save_guess")
def save_guess(data: dict, db: Session = Depends(get_db)):
    user_id = data.get("user_id")
    match_id = data.get("match_id")
    
    # Procura se já existe um palpite deste usuário para este jogo
    guess = db.query(models.Guess).filter(
        models.Guess.user_id == user_id,
        models.Guess.match_id == match_id
    ).first()

    if guess:
        # UPDATE: Se já existe, apenas atualiza os scores
        guess.score_1 = data.get("score_1")
        guess.score_2 = data.get("score_2")
    else:
        # INSERT: Se não existe, cria um novo registro
        guess = models.Guess(
            user_id=user_id,
            match_id=match_id,
            score_1=data.get("score_1"),
            score_2=data.get("score_2")
        )
        db.add(guess)

    db.commit()
    return {"status": "success"}

from sqlalchemy.orm import Session
from fastapi import Depends
import models

@app.get("/ranking")
def get_ranking(db: Session = Depends(get_db)):
    # 1. Pegamos todos os usuários, jogos e palpites do banco
    users = db.query(models.User).all()
    matches = db.query(models.Match).all()
    guesses = db.query(models.Guess).all()
    
    # Criamos um dicionário de matches para busca rápida por ID
    # Isso evita o "next(m for m in matches...)" que é lento
    matches_dict = {m.id: m for m in matches}
    
    ranking = []
    
    for user in users:
        points = 0
        # Filtra palpites deste usuário específico
        user_guesses = [g for g in guesses if g.user_id == user.id]
        
        for g in user_guesses:
            # Pega o jogo real do nosso dicionário
            m = matches_dict.get(g.match_id)
            
            # Só calcula se o jogo já tiver resultado oficial (score_1 não é None)
            if m and m.score_1 is not None:
                # Placar exato = 3 pontos
                if g.score_1 == m.score_1 and g.score_2 == m.score_2:
                    points += 3
                # Acertou o vencedor ou empate = 1 ponto
                else:
                    # Lógica de tendência (quem venceu ou se deu empate)
                    g_tendencia = (g.score_1 > g.score_2) - (g.score_1 < g.score_2)
                    m_tendencia = (m.score_1 > m.score_2) - (m.score_1 < m.score_2)
                    
                    if g_tendencia == m_tendencia:
                        points += 1
                        
        ranking.append({"name": user.name, "points": points})
    
    # Retorna ordenado do maior para o menor
    return sorted(ranking, key=lambda x: x['points'], reverse=True)


@app.get("/matches/{match_id}/guesses")
def get_match_guesses(match_id: int, db: Session = Depends(get_db)):
    # 1. Busca os palpites filtrando pelo ID do jogo
    guesses = db.query(models.Guess).filter(models.Guess.match_id == match_id).all()
    
    resultado = []
    for g in guesses:
        # 2. Busca o nome do usuário que fez o palpite
        user = db.query(models.User).filter(models.User.id == g.user_id).first()
        resultado.append({
            "user_name": user.name if user else "Anônimo",
            "score_1": g.score_1,
            "score_2": g.score_2
        })
    return resultado

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    # Busca no Banco de Dados em vez do JSON
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return {"user_id": user.id, "name": user.name}

@app.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    # Instead of reading JSON, we query the DB
    user = db.query(models.User).filter(
        models.User.name == data.get('username'),
        models.User.password == data.get('password')
    ).first()

    if user:
        return {"user_id": user.id, "name": user.name}
    raise HTTPException(status_code=401, detail="Invalid credentials")