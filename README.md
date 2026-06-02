# football-world-cup-pool
A football world cup pool app just for fun.

EXCLUINDO O BANCO ANTIGO
rm bolao.db

INICIALIZANDO O NOVO BANCO
python3 seed.py

RODANDO O BACKEND
uvicorn main:app --reload

RODANDO O FRONTEND
python3 -m http.server 8080

ACESSANDO O APP
http://localhost:8080/login.html

CHECANDO OS RESULTADOS DE TODAS AS PARTIDAS
sqlite3 bolao.db "SELECT id, team_1, team_2, score_1, score_2 FROM matches ORDER BY id;"

ATUALIZANDO O RESULTADO DE UMA PARTIDA
sqlite3 bolao.db "UPDATE matches SET score_1 = 2, score_2 = 1 WHERE id = 5;"

CHECANDO O RESULTADO ATUALIZADO
sqlite3 bolao.db "SELECT id, team_1, team_2, score_1, score_2 FROM matches WHERE id = 5;"