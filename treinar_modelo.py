import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline
from transformers import AutoTokenizer, AutoModel
import torch
import pickle
import os

# CARREGAR DATASET 
print("Carregando dataset...")
df = pd.read_csv('dataset_violencia_2000.csv')
print(f"Total de exemplos: {len(df)}")
print(df['tipo'].value_counts())
print(df['gravidade'].value_counts())

#  GERAR EMBEDDINGS COM BERT
print("\nCarregando modelo BERT português...")
MODEL_NAME = "neuralmind/bert-base-portuguese-cased"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Usando dispositivo: {device}")
model = model.to(device)
model.eval()

def gerar_embedding(textos, batch_size=32):
    embeddings = []
    for i in range(0, len(textos), batch_size):
        batch = textos[i:i+batch_size]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=128,
            return_tensors='pt'
        ).to(device)
        with torch.no_grad():
            outputs = model(**encoded)
            batch_embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()
        embeddings.extend(batch_embeddings)
        print(f"  Batch {i//batch_size + 1}/{len(textos)//batch_size + 1} processado")
    return np.array(embeddings)

print("\nGerando embeddings dos textos...")
X = gerar_embedding(df['texto'].tolist())
y_tipo = df['tipo'].values
y_gravidade = df['gravidade'].values

# TREINAR RANDOM FOREST - TIPO 
print("\nTreinando Random Forest para TIPO de violência...")
X_train, X_test, y_train, y_test = train_test_split(
    X, y_tipo, test_size=0.2, random_state=42, stratify=y_tipo
)

rf_tipo = RandomForestClassifier(
    n_estimators=200,
    max_depth=20,
    min_samples_split=2,
    random_state=42,
    n_jobs=-1
)
rf_tipo.fit(X_train, y_train)
y_pred = rf_tipo.predict(X_test)
print("\nResultados - TIPO de violência:")
print(classification_report(y_test, y_pred))

#  TREINAR RANDOM FOREST - GRAVIDADE
print("\nTreinando Random Forest para GRAVIDADE...")
X_train, X_test, y_train, y_test = train_test_split(
    X, y_gravidade, test_size=0.2, random_state=42, stratify=y_gravidade
)

rf_gravidade = RandomForestClassifier(
    n_estimators=200,
    max_depth=20,
    min_samples_split=2,
    random_state=42,
    n_jobs=-1
)
rf_gravidade.fit(X_train, y_train)
y_pred = rf_gravidade.predict(X_test)
print("\nResultados - GRAVIDADE:")
print(classification_report(y_test, y_pred))

#  SALVAR MODELOS 
print("\nSalvando modelos...")
os.makedirs('modelos', exist_ok=True)

with open('modelos/rf_tipo.pkl', 'wb') as f:
    pickle.dump(rf_tipo, f)

with open('modelos/rf_gravidade.pkl', 'wb') as f:
    pickle.dump(rf_gravidade, f)

print("Modelos salvos em /modelos/")
print("\nTreinamento concluído!")