from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import os

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
def get_matches():
    return read_json("matches.json")

@app.get("/guesses/{user_id}")
def get_user_guesses(user_id: int):
    all_guesses = read_json("guesses.json")
    return [g for g in all_guesses if g['user_id'] == user_id]

@app.post("/guesses")
def save_guess(new_guess: dict):
    guesses = read_json("guesses.json")
    # Atualiza se já existir, senão adiciona
    for g in guesses:
        if g['user_id'] == new_guess['user_id'] and g['match_id'] == new_guess['match_id']:
            g.update(new_guess)
            write_json("guesses.json", guesses)
            return {"status": "updated"}
    
    guesses.append(new_guess)
    write_json("guesses.json", guesses)
    return {"status": "created"}

@app.get("/ranking")
def get_ranking():
    users = read_json("users.json")
    matches = read_json("matches.json")
    guesses = read_json("guesses.json")
    
    ranking = []
    for user in users:
        points = 0
        user_guesses = [g for g in guesses if g['user_id'] == user['user_id']]
        for g in user_guesses:
            m = next((m for m in matches if m['match_id'] == g['match_id']), None)
            if m and m.get('score_1') is not None:
                # Lógica de pontos (mesma do JS, mas em Python)
                if g['score_1'] == m['score_1'] and g['score_2'] == m['score_2']:
                    points += 3
                elif (g['score_1'] > g['score_2']) == (m['score_1'] > m['score_2']) and \
                     (g['score_1'] < g['score_2']) == (m['score_1'] < m['score_2']):
                    points += 1
        ranking.append({"name": user['name'], "points": points})
    
    return sorted(ranking, key=lambda x: x['points'], reverse=True)


@app.get("/matches/{match_id}/guesses")
def get_match_guesses(match_id: int):
    guesses = read_json("guesses.json")
    users = read_json("users.json")
    
    # Filtra palpites desse jogo e anexa o nome do usuário
    resultado = []
    for g in guesses:
        if g['match_id'] == match_id:
            user = next((u for u in users if u['user_id'] == g['user_id']), None)
            resultado.append({
                "user_name": user['name'] if user else "Desconhecido",
                "score_1": g['score_1'],
                "score_2": g['score_2']
            })
    return resultado

@app.get("/users/{user_id}")
def get_user(user_id: int):
    users = read_json("users.json")
    user = next((u for u in users if u['user_id'] == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    # Retornamos apenas o que é necessário (segurança: não envie a senha aqui)
    return {"user_id": user['user_id'], "name": user['name']}

from fastapi import FastAPI, HTTPException, Body

@app.post("/login")
async def login(data: dict = Body(...)):
    # 1. Garante que os dados do JSON sejam lidos corretamente
    users = read_json("users.json")
    
    # 2. Extrai os dados enviados pelo frontend
    username_enviado = data.get('username')
    password_enviado = data.get('password')

    # 3. Busca o usuário (Verifique se no seu users.json a chave é 'name' ou 'username')
    user = next((u for u in users if u.get('name') == username_enviado and u.get('password') == password_enviado), None)
    
    if user:
        print(f"Login bem-sucedido para: {username_enviado}") # Log para você ver no terminal
        return {
            "status": "success", 
            "user_id": user['user_id'], 
            "name": user['name']
        }
    
    # 4. Caso falhe, logamos o erro no terminal para debug
    print(f"Tentativa de login falhou para: {username_enviado}")
    raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")