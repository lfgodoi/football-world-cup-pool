import json
import models
from database import SessionLocal, engine

# Cria as tabelas caso não existam
models.Base.metadata.create_all(bind=engine)

def seed_database():
    db = SessionLocal()
    try:
        # 1. Importar Usuários
        with open("users.json", "r", encoding="utf-8") as f:
            users_data = json.load(f)
            for u in users_data:
                # Verifica se o usuário já existe para não duplicar
                exists = db.query(models.User).filter(models.User.id == u['user_id']).first()
                if not exists:
                    new_user = models.User(
                        id=u['user_id'],
                        name=u['name'],
                        password=u['password'] # Em produção, use hash!
                    )
                    db.add(new_user)
        
        # 2. Importar Jogos
        with open("matches.json", "r", encoding="utf-8") as f:
            matches_data = json.load(f)
            for m in matches_data:
                exists = db.query(models.Match).filter(models.Match.id == m['match_id']).first()
                if not exists:
                    new_match = models.Match(
                        id=m['match_id'],
                        team_1=m['team_1'],
                        team_2=m['team_2'],
                        kickoff=m['kickoff'],
                        location=m.get('location', 'Estádio Indefinido'), # Pega do JSON ou define padrão
                        score_1=m.get('score_1'),
                        score_2=m.get('score_2')
                    )
                    db.add(new_match)

        db.commit()
        print("✅ Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao semear banco: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()