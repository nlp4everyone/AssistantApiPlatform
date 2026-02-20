# vLLM vs SGLang Performance Comparison

## Overview
This document compares the performance of vLLM (v0.15.1) and SGLang when running Qwen models with AWQ quantization.

## Performance Metrics

### Qwen/Qwen3-4B-AWQ

| Framework | Streaming | Non-Streaming |
|-----------|-----------|---------------|
| **vLLM** | 70 tokens/s | 100 tokens/s |
| **SGLang** | 73 tokens/s | 102 tokens/s |

**Winner:** SGLang (slightly better in both streaming and non-streaming)

### Qwen/Qwen3-8B-AWQ

| Framework | Streaming | Non-Streaming |
|-----------|-----------|---------------|
| **vLLM** | 46 tokens/s | 60 tokens/s |
| **SGLang** | 47 tokens/s | 60 tokens/s |

**Winner:** Tie (SGLang marginally better in streaming, identical in non-streaming)

## Key Findings

### 📊 Performance Summary
- **SGLang** shows consistently better or equal performance across all tested scenarios
- **4B Model**: SGLang leads by ~3-4% in both streaming and non-streaming
- **8B Model**: Performance is nearly identical, with minimal advantage to SGLang in streaming

### 🎯 Recommendations

#### Choose SGLang if:
- You need maximum throughput for 4B models
- You want consistent performance across different model sizes
- You're working with streaming applications

#### Consider vLLM if:
- You need broader ecosystem support and documentation
- You require more mature production features
- Performance differences are negligible for your use case

### 📈 Performance Trends
- Both frameworks handle 4B models significantly better than 8B models
- Non-streaming performance is consistently better than streaming for both frameworks
- The performance gap narrows with larger models (8B)

