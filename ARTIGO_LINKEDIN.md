**Do pacote bruto ao dado útil: o que aprendi construindo um pipeline para uma rede LoRa Meshtastic**

Nossa turma vem coletando pacotes de rádio Meshtastic num MongoDB. Ter os dados guardados não basta: nenhum pacote, sozinho, responde uma pergunta. Nesta atividade construí o pipeline que transforma "o que o rádio disse" em séries limpas e fáceis de consultar.

Encontrei quatro problemas escondidos no dado bruto:
1️⃣ Duplicatas: o mesmo pacote chega por caminhos diferentes. Deduplico por (nó, id do pacote), nunca pelo conteúdo.
2️⃣ Relógio errado: nós sem GPS mandam datas de 1970. Uso a hora de recebimento como referência.
3️⃣ Buracos: um nó que fica em silêncio também é informação. Registro o silêncio em vez de preencher a lacuna com valores inventados.
4️⃣ Esquema que muda: cada tipo de pacote traz campos diferentes. O que não bate vai para uma quarentena, onde é contado em vez de sumir.

Os dados vão para três destinos, cada um com sua pergunta: MariaDB com a série limpa ("o que aconteceu?"), MariaDB com os agregados ("como foi o período?") e Redis com o último valor ("e agora?").

Depois de 72 h rodando: [X] duplicatas descartadas, [Y] timestamps inválidos e [Z] pacotes na quarentena.

Código: [link do repositório] — obrigado, prof. Siriani!
#DataEngineering #IoT #Meshtastic #LoRa #MongoDB #Redis
