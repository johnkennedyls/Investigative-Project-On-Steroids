import pandas as pd
import numpy as np
import os
import torch
from sklearn.preprocessing import StandardScaler

def get_emergency_assets(data_path):
    # Leer un pedazo de la tabla maestra para reconstruir el vocabulario
    parquet_files = [f for f in os.listdir(data_path) if f.endswith('.parquet')]
    df = pd.read_parquet(os.path.join(data_path, parquet_files[0]))
    
    # 1. Reconstruir Vocabulario (Fingiendo el Tokenizer de entrenamiento)
    all_text = " ".join(df['lyrics_cleaned'].astype(str).tolist())
    words = sorted(list(set(all_text.split())))
    vocab = {word: i+2 for i, word in enumerate(words[:4998])} # Top 5k palabras
    vocab['<PAD>'] = 0
    vocab['<UNK>'] = 1
    
    # 2. Reconstruir Escalador Técnico
    # Suponiendo que las últimas 26 columnas son las features técnicas
    tech_cols = df.columns[-26:] 
    scaler = StandardScaler()
    scaler.fit(df[tech_cols])
    
    return vocab, scaler, df