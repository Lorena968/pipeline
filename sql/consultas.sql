-- 1) Tensão média da bateria de cada nó por dia (o nó solar está carregando?)
SELECT no_origem, DATE(periodo) AS dia, ROUND(media, 3) AS tensao_media, minimo, maximo
FROM lorena_agregado
WHERE granularidade = 'dia' AND metrica = 'voltage'
ORDER BY no_origem, dia;

-- 2) Utilização do canal por hora, média da malha (a malha está saturando? >25% é alerta)
SELECT periodo AS hora, ROUND(AVG(media), 2) AS util_canal_media, MAX(maximo) AS pico
FROM lorena_agregado
WHERE granularidade = 'hora' AND metrica = 'channel_utilization'
GROUP BY periodo
ORDER BY periodo;

-- 3) Quanto tempo cada nó ficou em silêncio (quem está caindo?)
SELECT no_origem, COUNT(*) AS silencios, SUM(minutos) AS minutos_total, MAX(minutos) AS maior_silencio
FROM lorena_silencios
GROUP BY no_origem
ORDER BY minutos_total DESC;

-- Contadores do requisito 2
SELECT nome, motivo, valor FROM lorena_contadores ORDER BY nome, valor DESC;
