import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
import pickle
import os

# ── CARREGAR DATASET ─────────────────────────────────────────────────────────
print("Carregando dataset...")
df = pd.read_csv('dataset_violencia_2000.csv')
print(f"Total de exemplos: {len(df)}")
print(df['tipo'].value_counts())
print(df['gravidade'].value_counts())

textos     = df['texto'].tolist()
y_tipo     = df['tipo'].values
y_gravidade = df['gravidade'].values

# ── PIPELINE TF-IDF + RANDOM FOREST ─────────────────────────────────────────
# TF-IDF com n-gramas de 1 a 3 palavras captura expressões como
# "me bateu", "ameacou de morte", "destruiu meus documentos"
# com desempenho muito próximo ao BERT para classificação de intenção
# e usando < 10 MB de RAM (vs ~450 MB do BERT).

print("\nTreinando Pipeline TF-IDF + RF para TIPO de violência...")
X_train, X_test, y_train, y_test = train_test_split(
    textos, y_tipo, test_size=0.2, random_state=42, stratify=y_tipo
)

pipeline_tipo = Pipeline([
    ("tfidf", TfidfVectorizer(
        ngram_range=(1, 3),       # unigramas, bigramas e trigramas
        max_features=50_000,      # vocabulário máximo
        sublinear_tf=True,        # aplica log na frequência — melhora RF
        min_df=2,                 # ignora tokens que aparecem < 2x
        analyzer="word",
        strip_accents=None,       # mantém acentos do português
    )),
    ("rf", RandomForestClassifier(
        n_estimators=300,
        max_depth=None,           # sem limite — TF-IDF é esparso, não precisa
        min_samples_split=2,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",  # compensa classes desbalanceadas
    )),
])

pipeline_tipo.fit(X_train, y_train)
y_pred = pipeline_tipo.predict(X_test)
print("\nResultados — TIPO de violência:")
print(classification_report(y_test, y_pred))

print("\nTreinando Pipeline TF-IDF + RF para GRAVIDADE...")
X_train, X_test, y_train, y_test = train_test_split(
    textos, y_gravidade, test_size=0.2, random_state=42, stratify=y_gravidade
)

pipeline_gravidade = Pipeline([
    ("tfidf", TfidfVectorizer(
        ngram_range=(1, 3),
        max_features=50_000,
        sublinear_tf=True,
        min_df=2,
        analyzer="word",
        strip_accents=None,
    )),
    ("rf", RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_split=2,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    )),
])

pipeline_gravidade.fit(X_train, y_train)
y_pred = pipeline_gravidade.predict(X_test)
print("\nResultados — GRAVIDADE:")
print(classification_report(y_test, y_pred))

# ── SALVAR ───────────────────────────────────────────────────────────────────
# Salvamos o Pipeline inteiro (TF-IDF + RF juntos)
# Em produção: pipeline_tipo.predict(["me bateu ontem"]) — sem pré-processamento
print("\nSalvando modelos...")
os.makedirs("modelos", exist_ok=True)

with open("modelos/rf_tipo.pkl", "wb") as f:
    pickle.dump(pipeline_tipo, f)

with open("modelos/rf_gravidade.pkl", "wb") as f:
    pickle.dump(pipeline_gravidade, f)

print("Modelos salvos em /modelos/")
print("\nTreinamento concluído!")
print(f"\nTamanho rf_tipo.pkl:     {os.path.getsize('modelos/rf_tipo.pkl') / 1e6:.1f} MB")
print(f"Tamanho rf_gravidade.pkl: {os.path.getsize('modelos/rf_gravidade.pkl') / 1e6:.1f} MB")