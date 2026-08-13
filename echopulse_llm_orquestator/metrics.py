# metrics.py
"""
Sistema de Métricas para EchoPulse AI
- Tracking de latencia por etapa
- Contadores de éxito/error
- Logs estructurados para análisis académico
"""
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from threading import Lock

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/metrics.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MetricsCollector:
    """Colector de métricas thread-safe para EchoPulse AI."""
    
    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.logs_dir / f"metrics_{datetime.now().strftime('%Y-%m')}.jsonl"
        self._lock = Lock()
        
        # Contadores en memoria
        self.counters = defaultdict(int)
        self.timings = defaultdict(list)
        self.errors = []
        
    def start_timer(self, stage: str) -> float:
        """Inicia timer para una etapa. Retorna timestamp de inicio."""
        return time.time()
    
    def end_timer(self, stage: str, start_time: float) -> float:
        """Finaliza timer y registra latencia en ms."""
        latency_ms = (time.time() - start_time) * 1000
        with self._lock:
            self.timings[stage].append(latency_ms)
            self.counters[f"{stage}_calls"] += 1
        logger.info(f"📊 [{stage}] {latency_ms:.1f}ms")
        return latency_ms
    
    def record_query(self, 
                     user_input: str,
                     query_en: str,
                     module3_results: list,
                     module2_results: list,
                     llm_response: str,
                     stage_latencies: dict,
                     success: bool = True,
                     error_msg: str = None):
        """Registra una consulta completa con todos sus metadatos."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input[:200],  # Truncar para privacidad
            "query_en": query_en,
            "success": success,
            "error": error_msg,
            "latencies_ms": stage_latencies,
            "total_latency_ms": sum(stage_latencies.values()),
            "module3": {
                "candidates_count": len(module3_results),
                "top_confidence": module3_results[0]["confidence"] if module3_results else None
            },
            "module2": {
                "candidates_count": len(module2_results),
                "top_score": module2_results[0].get("neural_score") if module2_results else None,
                "with_metadata": sum(1 for r in module2_results if r.get("track_name") != "Unknown")
            },
            "llm": {
                "response_length": len(llm_response) if llm_response else 0,
                "model": "Qwen/Qwen2.5-7B-Instruct"
            },
            "cache": {
                "metadata_hits": sum(1 for r in module2_results if r.get("source") == "kaggle_spotify_data_csv"),
                "metadata_misses": sum(1 for r in module2_results if r.get("track_name") == "Unknown")
            }
        }
        
        with self._lock:
            # Guardar en archivo JSONL (una línea por consulta)
            with open(self.metrics_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
            # Actualizar contadores
            self.counters["total_queries"] += 1
            if success:
                self.counters["successful_queries"] += 1
            else:
                self.counters["failed_queries"] += 1
                self.errors.append({"timestamp": record["timestamp"], "error": error_msg})
    
    def get_summary(self, last_n: int = None) -> dict:
        """Obtiene resumen estadístico de métricas."""
        with self._lock:
            summary = {
                "timestamp": datetime.now().isoformat(),
                "counters": dict(self.counters),
                "averages": {},
                "percentiles": {},
                "error_rate": 0.0
            }
            
            # Calcular promedios y percentiles por etapa
            for stage, latencies in self.timings.items():
                if latencies:
                    data = latencies[-last_n:] if last_n else latencies
                    summary["averages"][stage] = sum(data) / len(data)
                    sorted_data = sorted(data)
                    summary["percentiles"][stage] = {
                        "p50": sorted_data[len(sorted_data)//2],
                        "p90": sorted_data[int(len(sorted_data)*0.9)] if len(sorted_data) >= 10 else sorted_data[-1],
                        "p99": sorted_data[-1]
                    }
            
            # Tasa de error
            total = self.counters["total_queries"]
            if total > 0:
                summary["error_rate"] = self.counters["failed_queries"] / total * 100
            
            # Cobertura de metadatos
            if self.counters.get("module2_candidates_total", 0) > 0:
                summary["metadata_coverage"] = (
                    self.counters.get("metadata_hits", 0) / 
                    self.counters["module2_candidates_total"] * 100
                )
            
            return summary
    
    def export_report(self, output_path: str = None) -> str:
        """Exporta reporte académico en formato markdown."""
        if output_path is None:
            output_path = self.logs_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        
        summary = self.get_summary()
        
        report = f"""# 📊 Reporte de Métricas - EchoPulse AI
**Generado:** {summary['timestamp']}

## 🔢 Resumen Ejecutivo
| Métrica | Valor |
|---------|-------|
| Consultas totales | {summary['counters'].get('total_queries', 0)} |
| Tasa de éxito | {100 - summary['error_rate']:.2f}% |
| Cobertura de metadatos | {summary.get('metadata_coverage', 0):.1f}% |

## ⏱️ Latencia por Etapa (promedio)
| Etapa | Promedio (ms) | P90 (ms) | P99 (ms) |
|-------|--------------|----------|----------|
"""
        for stage in ["translation", "retrieval", "reranking", "generation"]:
            avg = summary['averages'].get(stage, 0)
            p90 = summary['percentiles'].get(stage, {}).get('p90', 0)
            p99 = summary['percentiles'].get(stage, {}).get('p99', 0)
            report += f"| {stage.capitalize()} | {avg:.1f} | {p90:.1f} | {p99:.1f} |\n"
        
        report += f"""
## 🎯 Calidad de Recomendación
| Módulo | Candidatos | Top-1 Confidence | Metadata Coverage |
|--------|-----------|-----------------|------------------|
| Módulo 3 (Intent) | {summary['counters'].get('module3_candidates_total', 0)} | - | - |
| Módulo 2 (Re-rank) | {summary['counters'].get('module2_candidates_total', 0)} | - | {summary.get('metadata_coverage', 0):.1f}% |

## ⚠️ Errores Recientes
"""
        if self.errors:
            for err in self.errors[-10:]:
                report += f"- `{err['timestamp']}`: {err['error']}\n"
        else:
            report += "*Sin errores registrados*\n"
        
        # Guardar reporte
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        logger.info(f"📄 Reporte exportado: {output_path}")
        return str(output_path)

# Instancia global para usar en app.py
metrics = MetricsCollector()