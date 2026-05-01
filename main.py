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
def login(data: dict, db: Session = Depends(get_db)):
    # Instead of reading JSON, we query the DB
    user = db.query(models.User).filter(
        models.User.name == data.get('username'),
        models.User.password == data.get('password')
    ).first()

    if user:
        return {"user_id": user.id, "name": user.name}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/register")
def register(data: dict, db: Session = Depends(get_db)):
    # 1. Extração dos dados
    username = data.get("name")
    password = data.get("password")
    question = data.get("security_question")
    answer = data.get("security_answer")

    # 2. Validação básica (evita salvar campos vazios no banco)
    if not all([username, password, question, answer]):
        raise HTTPException(
            status_code=400, 
            detail="Todos os campos são obrigatórios (nome, senha, pergunta e resposta)."
        )

    # 3. Verifica se o nome já existe (case-insensitive para evitar 'Admin' e 'admin')
    existing_user = db.query(models.User).filter(models.User.name == username).first()
    if existing_user:
        raise HTTPException(
            status_code=400, 
            detail="Este nome de usuário já está em uso."
        )

    # 4. Criação do novo usuário
    new_user = models.User(
        name=username,
        password=password,
        security_question=question,
        security_answer=answer
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
    except Exception as e:
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
def update_user(user_id: int, data: dict, db: Session = Depends(get_db)):
    """
    Atualiza o perfil do usuário: permite alterar username e/ou password
    """
    new_name = data.get("name")
    new_password = data.get("password")
    
    # Busca o usuário
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Se novo nome for fornecido, verifica se já está em uso (por outro usuário)
    if new_name and new_name != user.name:
        existing = db.query(models.User).filter(models.User.name == new_name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Este nome de usuário já está em uso")
        user.name = new_name
    
    # Se nova senha for fornecida, atualiza
    if new_password:
        user.password = new_password
    
    try:
        db.commit()
        db.refresh(user)
        return {
            "status": "success", 
            "message": "Perfil atualizado com sucesso",
            "user_id": user.id,
            "name": user.name
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao atualizar perfil")

# ==================== GROUP ENDPOINTS ====================

@app.post("/groups")
def create_group(data: dict, db: Session = Depends(get_db)):
    """Cria um novo grupo"""
    name = data.get("name")
    user_id = data.get("user_id")
    
    if not name or not user_id:
        raise HTTPException(status_code=400, detail="Nome do grupo e ID do usuário são obrigatórios")
    
    # Verifica se o grupo já existe
    existing = db.query(models.Group).filter(models.Group.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Este nome de grupo já está em uso")
    
    from datetime import datetime
    new_group = models.Group(
        name=name,
        created_by=user_id,
        created_at=datetime.now().isoformat()
    )
    
    try:
        db.add(new_group)
        db.commit()
        db.refresh(new_group)
        
        # Adiciona o criador como admin do grupo
        db.execute(models.user_groups.insert().values(
            user_id=user_id,
            group_id=new_group.id,
            role='admin'
        ))
        db.commit()
        
        return {
            "status": "success",
            "group_id": new_group.id,
            "group_name": new_group.name
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao criar grupo")

@app.get("/groups")
def get_all_groups(db: Session = Depends(get_db)):
    """Lista todos os grupos disponíveis"""
    groups = db.query(models.Group).all()
    return [{"id": g.id, "name": g.name} for g in groups]

@app.get("/groups/user/{user_id}")
def get_user_groups(user_id: int, db: Session = Depends(get_db)):
    """Lista os grupos que o usuário participa"""
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
def join_group(group_id: int, data: dict, db: Session = Depends(get_db)):
    """Adiciona um usuário ao grupo"""
    user_id = data.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="ID do usuário é obrigatório")
    
    # Verifica se o grupo existe
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    # Verifica se o usuário já está no grupo
    existing = db.execute(
        models.user_groups.select().where(
            models.user_groups.c.user_id == user_id,
            models.user_groups.c.group_id == group_id
        )
    ).fetchone()
    
    if existing:
        raise HTTPException(status_code=400, detail="Usuário já está neste grupo")
    
    try:
        db.execute(models.user_groups.insert().values(
            user_id=user_id,
            group_id=group_id,
            role='member'
        ))
        db.commit()
        return {"status": "success", "message": "Você entrou no grupo com sucesso!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao entrar no grupo")

@app.delete("/groups/{group_id}/leave")
def leave_group(group_id: int, data: dict, db: Session = Depends(get_db)):
    """Remove um usuário do grupo"""
    user_id = data.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="ID do usuário é obrigatório")
    
    # Verifica se o grupo existe
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    # O criador não pode sair do grupo
    if group.created_by == user_id:
        raise HTTPException(status_code=400, detail="O criador não pode sair do grupo. Exclua o grupo instead.")
    
    try:
        db.execute(
            models.user_groups.delete().where(
                models.user_groups.c.user_id == user_id,
                models.user_groups.c.group_id == group_id
            )
        )
        db.commit()
        return {"status": "success", "message": "Você saiu do grupo com sucesso!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao sair do grupo")

@app.delete("/groups/{group_id}")
def delete_group(group_id: int, data: dict, db: Session = Depends(get_db)):
    """Exclui um grupo (apenas pelo admin)"""
    user_id = data.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="ID do usuário é obrigatório")
    
    # Verifica se o grupo existe
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    # Verifica se o usuário é o admin
    membership = db.execute(
        models.user_groups.select().where(
            models.user_groups.c.user_id == user_id,
            models.user_groups.c.group_id == group_id,
            models.user_groups.c.role == 'admin'
        )
    ).fetchone()
    
    if not membership:
        raise HTTPException(status_code=403, detail="Apenas o admin pode excluir o grupo")
    
    try:
        # Remove todos os membros
        db.execute(
            models.user_groups.delete().where(models.user_groups.c.group_id == group_id)
        )
        # Remove o grupo
        db.delete(group)
        db.commit()
        return {"status": "success", "message": "Grupo excluído com sucesso!"}
    except Exception as e:
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