from fastapi import Depends, FastAPI, HTTPException, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import uuid
import hashlib
import binascii
import datetime
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

# Permite que seu Frontend acesse o Backend de forma controlada
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Sessões em memória para tokens de autenticação
SESSIONS = {}

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{binascii.hexlify(salt).decode()}${binascii.hexlify(hashed).decode()}"


def verify_password(stored_password: str, provided_password: str) -> bool:
    if not stored_password or not provided_password:
        return False
    if '$' not in stored_password:
        return stored_password == provided_password
    salt_hex, hash_hex = stored_password.split('$', 1)
    salt = binascii.unhexlify(salt_hex.encode())
    expected_hash = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
    return binascii.hexlify(expected_hash).decode() == hash_hex


def create_session(user_id: int) -> str:
    token = uuid.uuid4().hex
    SESSIONS[token] = {
        "user_id": user_id,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    return token


def get_token_from_header(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    return parts[1]


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)):
    token = get_token_from_header(authorization)
    session = SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida ou expirada")
    user = db.query(models.User).filter(models.User.id == session["user_id"]).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário da sessão não encontrado")
    return user


def match_has_started(match) -> bool:
    if not match.kickoff:
        return False
    try:
        kickoff_time = datetime.datetime.fromisoformat(match.kickoff)
        return datetime.datetime.utcnow() >= kickoff_time
    except ValueError:
        return False

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
def get_user_guesses(user_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado aos palpites de outro usuário")

    guesses = db.query(models.Guess).filter(models.Guess.user_id == user_id).all()
    return guesses

@app.post("/save_guess")
def save_guess(data: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    match_id = data.get("match_id")
    score_1 = data.get("score_1")
    score_2 = data.get("score_2")

    if match_id is None or score_1 is None or score_2 is None:
        raise HTTPException(status_code=400, detail="match_id, score_1 e score_2 são obrigatórios")

    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Partida não encontrada")

    if match.score_1 is not None or match.score_2 is not None or match_has_started(match):
        raise HTTPException(
            status_code=403,
            detail="Palpites não podem ser salvos ou alterados após o início da partida ou depois que o resultado oficial estiver definido."
        )

    guess = db.query(models.Guess).filter(
        models.Guess.user_id == current_user.id,
        models.Guess.match_id == match_id
    ).first()

    if guess:
        guess.score_1 = score_1
        guess.score_2 = score_2
    else:
        guess = models.Guess(
            user_id=current_user.id,
            match_id=match_id,
            score_1=score_1,
            score_2=score_2
        )
        db.add(guess)

    db.commit()
    return {"status": "success"}

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
def get_match_guesses(match_id: int, group_id: int | None = None, db: Session = Depends(get_db)):
    # 1. Busca os palpites filtrando pelo ID do jogo
    query = db.query(models.Guess).filter(models.Guess.match_id == match_id)

    if group_id is not None:
        result = db.execute(
            models.user_groups.select().where(models.user_groups.c.group_id == group_id)
        ).fetchall()
        member_ids = [r.user_id for r in result]

        if not member_ids:
            return []

        query = query.filter(models.Guess.user_id.in_(member_ids))

    guesses = query.all()
    
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
    return {
        "user_id": user.id, 
        "name": user.name,
        "security_question": user.security_question
    }

@app.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    """Lista todos os usuários (para recuperação de senha)"""
    users = db.query(models.User).all()
    return [{"id": u.id, "name": u.name} for u in users]

@app.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido ou malformado")

    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        raise HTTPException(status_code=400, detail="Usuário e senha são obrigatórios")

    user = db.query(models.User).filter(models.User.name == username).first()
    if not user or not verify_password(user.password, password):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")

    if '$' not in user.password:
        user.password = hash_password(password)
        db.commit()

    token = create_session(user.id)
    return {"user_id": user.id, "name": user.name, "token": token}

@app.post("/logout")
def logout(authorization: str = Header(None)):
    token = get_token_from_header(authorization)
    if token in SESSIONS:
        del SESSIONS[token]
    return {"status": "success", "message": "Logout realizado"}

@app.post("/register")
def register(data: dict, db: Session = Depends(get_db)):
    username = data.get("name")
    password = data.get("password")
    question = data.get("security_question")
    answer = data.get("security_answer")

    if not all([username, password, question, answer]):
        raise HTTPException(
            status_code=400,
            detail="Todos os campos são obrigatórios (nome, senha, pergunta e resposta)."
        )

    existing_user = db.query(models.User).filter(models.User.name == username).first()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Este nome de usuário já está em uso."
        )

    new_user = models.User(
        name=username,
        password=hash_password(password),
        security_question=question,
        security_answer=answer.strip()
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {
            "status": "success",
            "message": "Usuário criado com sucesso",
            "user_id": new_user.id
        }
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao salvar no banco de dados."
        )

@app.post("/forgot_password")
def forgot_password(data: dict, db: Session = Depends(get_db)):
    """
    Recuperação de senha:用户提供用户名和安全问题答案来重置密码
    """
    username = data.get("username")
    security_answer = data.get("security_answer")
    new_password = data.get("new_password")

    # 1. Validação básica
    if not all([username, security_answer, new_password]):
        raise HTTPException(
            status_code=400, 
            detail="Todos os campos são obrigatórios."
        )

    # 2. Busca o usuário
    user = db.query(models.User).filter(models.User.name == username).first()
    if not user:
        raise HTTPException(
            status_code=404, 
            detail="Usuário não encontrado."
        )

    # 3. Verifica a resposta de segurança (case-insensitive)
    if user.security_answer.lower() != security_answer.lower():
        raise HTTPException(
            status_code=401, 
            detail="Resposta de segurança incorreta."
        )

    # 4. Atualiza a senha
    user.password = new_password
    
    try:
        db.commit()
        return {
            "status": "success", 
            "message": "Senha alterada com sucesso! Agora você pode fazer login."
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail="Erro ao atualizar a senha."
        )

@app.put("/users/{user_id}")
def update_user(user_id: int, data: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Atualiza o perfil do usuário: permite alterar username e/ou password
    """
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Você só pode atualizar seu próprio perfil")

    new_name = data.get("name")
    new_password = data.get("password")
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    if new_name and new_name != user.name:
        existing = db.query(models.User).filter(models.User.name == new_name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Este nome de usuário já está em uso")
        user.name = new_name
    
    if new_password:
        user.password = hash_password(new_password)
    
    try:
        db.commit()
        db.refresh(user)
        return {
            "status": "success",
            "message": "Perfil atualizado com sucesso",
            "user_id": user.id,
            "name": user.name
        }
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao atualizar perfil")

# ==================== GROUP ENDPOINTS ====================

@app.post("/groups")
def create_group(data: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cria um novo grupo"""
    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Nome do grupo é obrigatório")
    
    existing = db.query(models.Group).filter(models.Group.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Este nome de grupo já está em uso")
    
    from datetime import datetime
    new_group = models.Group(
        name=name,
        created_by=current_user.id,
        created_at=datetime.now().isoformat()
    )
    
    try:
        db.add(new_group)
        db.commit()
        db.refresh(new_group)
        
        db.execute(models.user_groups.insert().values(
            user_id=current_user.id,
            group_id=new_group.id,
            role='admin'
        ))
        db.commit()
        
        return {
            "status": "success",
            "group_id": new_group.id,
            "group_name": new_group.name
        }
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao criar grupo")

@app.get("/groups")
def get_all_groups(db: Session = Depends(get_db)):
    """Lista todos os grupos disponíveis"""
    groups = db.query(models.Group).all()
    return [{"id": g.id, "name": g.name} for g in groups]

@app.get("/groups/user/{user_id}")
def get_user_groups(user_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lista os grupos que o usuário participa"""
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado aos grupos de outro usuário")

    result = db.execute(
        models.user_groups.select().where(models.user_groups.c.user_id == user_id)
    ).fetchall()
    
    groups = []
    for r in result:
        group = db.query(models.Group).filter(models.Group.id == r.group_id).first()
        if group:
            groups.append({
                "id": group.id,
                "name": group.name,
                "role": r.role,
                "created_by": group.created_by
            })
    return groups

@app.post("/groups/{group_id}/join")
def join_group(group_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    existing = db.execute(
        models.user_groups.select().where(
            models.user_groups.c.user_id == current_user.id,
            models.user_groups.c.group_id == group_id
        )
    ).fetchone()
    
    if existing:
        raise HTTPException(status_code=400, detail="Você já está neste grupo")
    
    try:
        db.execute(models.user_groups.insert().values(
            user_id=current_user.id,
            group_id=group_id,
            role='member'
        ))
        db.commit()
        return {"status": "success", "message": "Você entrou no grupo com sucesso!"}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao entrar no grupo")

@app.delete("/groups/{group_id}/leave")
def leave_group(group_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    if group.created_by == current_user.id:
        raise HTTPException(status_code=400, detail="O criador não pode sair do grupo. Exclua o grupo em vez disso.")
    
    try:
        db.execute(
            models.user_groups.delete().where(
                models.user_groups.c.user_id == current_user.id,
                models.user_groups.c.group_id == group_id
            )
        )
        db.commit()
        return {"status": "success", "message": "Você saiu do grupo com sucesso!"}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao sair do grupo")

@app.delete("/groups/{group_id}")
def delete_group(group_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    membership = db.execute(
        models.user_groups.select().where(
            models.user_groups.c.user_id == current_user.id,
            models.user_groups.c.group_id == group_id,
            models.user_groups.c.role == 'admin'
        )
    ).fetchone()
    
    if not membership:
        raise HTTPException(status_code=403, detail="Apenas o admin pode excluir o grupo")
    
    try:
        db.execute(
            models.user_groups.delete().where(models.user_groups.c.group_id == group_id)
        )
        db.delete(group)
        db.commit()
        return {"status": "success", "message": "Grupo excluído com sucesso!"}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao excluir grupo")

@app.get("/groups/{group_id}/members")
def get_group_members(group_id: int, db: Session = Depends(get_db)):
    """Lista os membros de um grupo"""
    # Verifica se o grupo existe
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    result = db.execute(
        models.user_groups.select().where(models.user_groups.c.group_id == group_id)
    ).fetchall()
    
    members = []
    for r in result:
        user = db.query(models.User).filter(models.User.id == r.user_id).first()
        if user:
            members.append({
                "user_id": user.id,
                "name": user.name,
                "role": r.role
            })
    return members

@app.get("/groups/{group_id}/ranking")
def get_group_ranking(group_id: int, db: Session = Depends(get_db)):
    """Retorna o ranking apenas dos membros do grupo"""
    # Pega todos os membros do grupo
    result = db.execute(
        models.user_groups.select().where(models.user_groups.c.group_id == group_id)
    ).fetchall()
    
    member_ids = [r.user_id for r in result]
    
    if not member_ids:
        return []
    
    # Pega usuários do banco
    users = db.query(models.User).filter(models.User.id.in_(member_ids)).all()
    matches = db.query(models.Match).all()
    guesses = db.query(models.Guess).all()
    
    matches_dict = {m.id: m for m in matches}
    
    ranking = []
    
    for user in users:
        points = 0
        user_guesses = [g for g in guesses if g.user_id == user.id]
        
        for g in user_guesses:
            m = matches_dict.get(g.match_id)
            
            if m and m.score_1 is not None:
                if g.score_1 == m.score_1 and g.score_2 == m.score_2:
                    points += 3
                else:
                    g_tendencia = (g.score_1 > g.score_2) - (g.score_1 < g.score_2)
                    m_tendencia = (m.score_1 > m.score_2) - (m.score_1 < m.score_2)
                    
                    if g_tendencia == m_tendencia:
                        points += 1
                        
        ranking.append({"name": user.name, "points": points})
    
    return sorted(ranking, key=lambda x: x['points'], reverse=True)