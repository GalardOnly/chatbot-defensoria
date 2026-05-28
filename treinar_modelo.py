import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_validate
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_recall_curve,
)
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
import joblib
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

np.random.seed(42)

COLUNAS_OBRIGATORIAS = {"texto", "tipo", "gravidade"}


def carregar_dataset_treinamento() -> tuple[pd.DataFrame, list[str]]:
    """
    Usa o dataset unificado quando existe.
    Ele já consolida violência doméstica, transfobia, stalking e fachada.
    """
    if os.path.exists("dataset_unificado.csv"):
        print("Carregando dataset_unificado.csv...")
        return pd.read_csv("dataset_unificado.csv"), ["dataset_unificado.csv"]

    if not os.path.exists("dataset_violencia_2000.csv"):
        raise FileNotFoundError(
            "Nenhum dataset encontrado. Esperado dataset_unificado.csv ou dataset_violencia_2000.csv."
        )

    print("Carregando dataset_violencia_2000.csv...")
    df_base = pd.read_csv("dataset_violencia_2000.csv")
    fontes = ["dataset_violencia_2000.csv"]

    if os.path.exists("dataset_trans.csv"):
        print("Carregando dataset_trans.csv...")
        df_trans = pd.read_csv("dataset_trans.csv")
        colunas_trans = {"texto", "categoria", "severidade"}
        ausentes_trans = colunas_trans - set(df_trans.columns)
        if ausentes_trans:
            raise ValueError(
                f"Colunas ausentes no dataset_trans.csv: {ausentes_trans}. "
                f"Encontradas: {list(df_trans.columns)}"
            )

        mapa_tipo_trans = {
            "violencia_fisica": "fisica",
            "violencia_moral": "moral",
            "violencia_patrimonial": "patrimonial",
            "violencia_psicologica": "psicologica",
            "violencia_sexual": "sexual",
            "stalking": "stalking",
        }
        mapa_gravidade_trans = {
            "leve": "baixa",
            "moderada": "media",
            "grave": "alta",
        }
        df_trans = df_trans.rename(columns={"categoria": "tipo", "severidade": "gravidade"})
        df_trans["tipo"] = df_trans["tipo"].map(mapa_tipo_trans)
        df_trans["gravidade"] = df_trans["gravidade"].map(mapa_gravidade_trans)
        invalidas = df_trans[df_trans[["tipo", "gravidade"]].isna().any(axis=1)]
        if not invalidas.empty:
            raise ValueError(
                "dataset_trans.csv contem categoria/severidade sem mapeamento: "
                f"{invalidas[['texto', 'tipo', 'gravidade']].head().to_dict(orient='records')}"
            )
        df_base = pd.concat([df_base, df_trans[["texto", "tipo", "gravidade"]]], ignore_index=True)
        fontes.append("dataset_trans.csv")
        print(f"  Exemplos trans adicionados ao treinamento: {len(df_trans)}")

    return df_base, fontes


print("Carregando dataset...")
df, fontes_dataset = carregar_dataset_treinamento()
ausentes = COLUNAS_OBRIGATORIAS - set(df.columns)
if ausentes:
    raise ValueError(f"Colunas ausentes no CSV: {ausentes}. Encontradas: {list(df.columns)}")

antes = len(df)
df = df.dropna(subset=["texto", "tipo", "gravidade"])
df = df[df["texto"].str.strip() != ""]
if len(df) < antes:
    print(f"  Aviso: {antes - len(df)} linha(s) removida(s).")

print(f"Total de exemplos validos: {len(df)}")
print("\nDistribuicao TIPO:"); print(df['tipo'].value_counts())
print("\nDistribuicao GRAVIDADE:"); print(df['gravidade'].value_counts())
if "origem" in df.columns:
    print("\nDistribuicao ORIGEM:"); print(df["origem"].value_counts())

textos      = df['texto'].tolist()
y_tipo      = df['tipo'].values
y_gravidade = df['gravidade'].values

def criar_vetorizador():
    return TfidfVectorizer(
        ngram_range=(1, 3), max_features=50_000,
        sublinear_tf=True, min_df=2,
        analyzer="word", strip_accents=None,
    )


def criar_pipeline_tipo():
    return Pipeline([
        ("tfidf", criar_vetorizador()),
        ("clf", OneVsRestClassifier(
            LogisticRegression(
                max_iter=2_000,
                class_weight="balanced",
                C=2,
                solver="liblinear",
                random_state=42,
            ),
            n_jobs=1,
        )),
    ])


def criar_pipeline_gravidade():
    return Pipeline([
        ("tfidf", criar_vetorizador()),
        ("rf", RandomForestClassifier(
            n_estimators=300, max_depth=None,
            min_samples_split=2, random_state=42,
            n_jobs=-1, class_weight="balanced",
        )),
    ])

RECALL_MINIMO_ALTA = 0.92

def ajustar_limiar_recall(pipeline_aval, X_test, y_test, classe_alvo, recall_minimo):
    classes    = list(pipeline_aval.classes_)
    idx        = classes.index(classe_alvo)
    y_prob     = pipeline_aval.predict_proba(X_test)[:, idx]
    y_bin      = (y_test == classe_alvo).astype(int)
    prec, rec, limiares = precision_recall_curve(y_bin, y_prob)
    prec_al, rec_al = prec[:-1], rec[:-1]
    candidatos = [
        (lim, p, r) for lim, p, r in zip(limiares, prec_al, rec_al)
        if r >= recall_minimo
    ]
    if not candidatos:
        print(f"  AVISO: nenhum limiar alcanca recall={recall_minimo:.0%} para '{classe_alvo}'. Usando 0.5.")
        return 0.5
    melhor = max(candidatos, key=lambda x: x[1])
    print(f"  Limiar ajustado '{classe_alvo}': {melhor[0]:.4f} -> Recall={melhor[2]:.4f}, Precisao={melhor[1]:.4f}")
    return float(melhor[0])

CV = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
SCORING = {"f1_weighted": "f1_weighted", "accuracy": "accuracy"}


def metricas_basicas(y_true, y_pred) -> dict:
    return {
        "acuracia": round(float(accuracy_score(y_true, y_pred)), 4),
        "f1_weighted": round(float(f1_score(y_true, y_pred, average="weighted", zero_division=0)), 4),
    }


def avaliar_recorte_origem(nome: str, df_teste: pd.DataFrame, y_true, y_pred) -> dict | None:
    if "origem" not in df_teste.columns:
        return None
    mask = df_teste["origem"].astype(str).str.contains(nome, case=False, na=False).to_numpy()
    if not mask.any():
        return None
    metricas = metricas_basicas(np.asarray(y_true)[mask], np.asarray(y_pred)[mask])
    metricas["amostras"] = int(mask.sum())
    return metricas

print("\n─────────────────────────────────────────────────")
print("Treinando TIPO de violencia (CV-5)...")
pipeline_tipo = criar_pipeline_tipo()
cv_tipo = cross_validate(pipeline_tipo, textos, y_tipo, cv=CV, scoring=SCORING, n_jobs=-1)
scores_tipo = cv_tipo["test_f1_weighted"]
scores_tipo_acc = cv_tipo["test_accuracy"]
print(f"  Acuracia media: {scores_tipo_acc.mean():.4f} +/- {scores_tipo_acc.std():.4f}")
print(f"  F1 medio:       {scores_tipo.mean():.4f} +/- {scores_tipo.std():.4f}")
pipeline_tipo.fit(textos, y_tipo)

df_train_t, df_test_t = train_test_split(
    df, test_size=0.2, random_state=42, stratify=df["tipo"])
X_train_t = df_train_t["texto"].tolist()
X_test_t = df_test_t["texto"].tolist()
y_train_t = df_train_t["tipo"].values
y_test_t = df_test_t["tipo"].values
p_tipo_aval = criar_pipeline_tipo(); p_tipo_aval.fit(X_train_t, y_train_t)
y_pred_t = p_tipo_aval.predict(X_test_t)
metricas_tipo_holdout = metricas_basicas(y_test_t, y_pred_t)
print("\nRelatorio hold-out TIPO:")
print(classification_report(y_test_t, y_pred_t, zero_division=0))
print(f"Acuracia hold-out TIPO: {metricas_tipo_holdout['acuracia']:.4f}")
recorte_tipo_trans = avaliar_recorte_origem("trans", df_test_t, y_test_t, y_pred_t)
if recorte_tipo_trans:
    print(
        "Recorte origem trans TIPO: "
        f"n={recorte_tipo_trans['amostras']} | "
        f"acuracia={recorte_tipo_trans['acuracia']:.4f} | "
        f"F1={recorte_tipo_trans['f1_weighted']:.4f}"
    )

print("─────────────────────────────────────────────────")
print("Treinando GRAVIDADE (CV-5)...")
pipeline_gravidade = criar_pipeline_gravidade()
cv_grav = cross_validate(pipeline_gravidade, textos, y_gravidade, cv=CV, scoring=SCORING, n_jobs=-1)
scores_grav = cv_grav["test_f1_weighted"]
scores_grav_acc = cv_grav["test_accuracy"]
print(f"  Acuracia media: {scores_grav_acc.mean():.4f} +/- {scores_grav_acc.std():.4f}")
print(f"  F1 medio:       {scores_grav.mean():.4f} +/- {scores_grav.std():.4f}")
pipeline_gravidade.fit(textos, y_gravidade)

df_train_g, df_test_g = train_test_split(
    df, test_size=0.2, random_state=42, stratify=df["gravidade"])
X_train_g = df_train_g["texto"].tolist()
X_test_g = df_test_g["texto"].tolist()
y_train_g = df_train_g["gravidade"].values
y_test_g = df_test_g["gravidade"].values
p_grav_aval = criar_pipeline_gravidade(); p_grav_aval.fit(X_train_g, y_train_g)
y_pred_g = p_grav_aval.predict(X_test_g)
metricas_grav_holdout = metricas_basicas(y_test_g, y_pred_g)
print("\nRelatorio hold-out GRAVIDADE (limiar 0.5):")
print(classification_report(y_test_g, y_pred_g, zero_division=0))
print(f"Acuracia hold-out GRAVIDADE: {metricas_grav_holdout['acuracia']:.4f}")
recorte_grav_trans = avaliar_recorte_origem("trans", df_test_g, y_test_g, y_pred_g)
if recorte_grav_trans:
    print(
        "Recorte origem trans GRAVIDADE: "
        f"n={recorte_grav_trans['amostras']} | "
        f"acuracia={recorte_grav_trans['acuracia']:.4f} | "
        f"F1={recorte_grav_trans['f1_weighted']:.4f}"
    )

print(f"\nAjustando limiar para recall minimo {RECALL_MINIMO_ALTA:.0%} na classe 'alta'...")
limiar_alta = ajustar_limiar_recall(p_grav_aval, X_test_g, y_test_g, "alta", RECALL_MINIMO_ALTA)

classes_grav = list(p_grav_aval.classes_)
idx_alta     = classes_grav.index("alta")
y_prob_g     = p_grav_aval.predict_proba(X_test_g)
y_pred_aj    = [
    "alta" if probs[idx_alta] >= limiar_alta else classes_grav[np.argmax(probs)]
    for probs in y_prob_g
]
print(f"\nRelatorio hold-out GRAVIDADE (limiar ajustado {limiar_alta:.4f} para 'alta'):")
print(classification_report(y_test_g, y_pred_aj, zero_division=0))
metricas_grav_ajustada = metricas_basicas(y_test_g, y_pred_aj)
print(f"Acuracia hold-out GRAVIDADE ajustada: {metricas_grav_ajustada['acuracia']:.4f}")

def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65_536), b""):
            h.update(bloco)
    return h.hexdigest()

print("\nSalvando modelos...")
os.makedirs("modelos", exist_ok=True)

MODELOS = {
    "rf_tipo":      ("modelos/rf_tipo.joblib",     pipeline_tipo),
    "rf_gravidade": ("modelos/rf_gravidade.joblib", pipeline_gravidade),
}

manifest = {
    "gerado_em":    datetime.now(timezone.utc).isoformat(),
    "sklearn_seed": 42, "numpy_seed": 42, "cv_folds": 5,
    "dataset": {
        "fontes": fontes_dataset,
        "total_exemplos": int(len(df)),
        "distribuicao_tipo": df["tipo"].value_counts().to_dict(),
        "distribuicao_gravidade": df["gravidade"].value_counts().to_dict(),
        "distribuicao_origem": df["origem"].value_counts().to_dict() if "origem" in df.columns else {},
    },
    "algoritmos": {
        "tipo": "TfidfVectorizer + OneVsRest LogisticRegression",
        "gravidade": "TfidfVectorizer + RandomForestClassifier",
    },
    "limiares": {
        "gravidade_alta":        limiar_alta,
        "recall_minimo_alta":    RECALL_MINIMO_ALTA,
        "tipo_confianca_padrao": 0.60,
    },
    "metricas": {
        "tipo_acuracia_cv_media": round(float(scores_tipo_acc.mean()), 4),
        "tipo_acuracia_cv_desvio": round(float(scores_tipo_acc.std()), 4),
        "tipo_f1_cv_media":       round(float(scores_tipo.mean()), 4),
        "tipo_f1_cv_desvio":      round(float(scores_tipo.std()),  4),
        "tipo_acuracia_holdout": metricas_tipo_holdout["acuracia"],
        "tipo_f1_holdout": metricas_tipo_holdout["f1_weighted"],
        "tipo_recorte_trans": recorte_tipo_trans,
        "gravidade_acuracia_cv_media": round(float(scores_grav_acc.mean()), 4),
        "gravidade_acuracia_cv_desvio": round(float(scores_grav_acc.std()), 4),
        "gravidade_f1_cv_media":  round(float(scores_grav.mean()), 4),
        "gravidade_f1_cv_desvio": round(float(scores_grav.std()),  4),
        "gravidade_acuracia_holdout": metricas_grav_holdout["acuracia"],
        "gravidade_f1_holdout": metricas_grav_holdout["f1_weighted"],
        "gravidade_acuracia_holdout_ajustada": metricas_grav_ajustada["acuracia"],
        "gravidade_f1_holdout_ajustada": metricas_grav_ajustada["f1_weighted"],
        "gravidade_recorte_trans": recorte_grav_trans,
    },
    "arquivos": {},
}

for nome, (caminho, pipeline) in MODELOS.items():
    joblib.dump(pipeline, caminho, compress=3)
    digest = sha256_arquivo(caminho)
    mb     = os.path.getsize(caminho) / 1e6
    manifest["arquivos"][nome] = {"caminho": caminho, "sha256": digest, "tamanho_mb": round(mb, 2)}
    print(f"  {caminho}  ({mb:.1f} MB)  sha256={digest[:16]}...")

with open("modelos/modelos.manifest.json", "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print(f"\nManifesto salvo. Limiar 'alta': {limiar_alta:.4f} (recall minimo: {RECALL_MINIMO_ALTA:.0%})")
print("Treinamento concluido!")
print("\n[!] Adicione modelos/*.joblib ao .gitignore antes de fazer commit.")
