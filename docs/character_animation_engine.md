# Character Animation Engine (rig 2D por deformación)

Motor determinista para animar a Akira y Daniela a partir de sus imágenes maestras pintadas, sin generación por IA. Vive en `src/huellas_engine/character_animation/` y es independiente del piloto LTX (`animation_engine.py`).

## Por qué no recortar y rotar la cabeza (V1/V2)

Los prototipos `scripts/prototype_akira_rig*.py` recortaban la cabeza y la rotaban sobre el cuerpo. Fallaban por tres motivos verificados:

1. **Hueco bajo la cabeza**: el cuerpo se quedaba sin los píxeles de la cabeza; al rotar, quedaba a la vista una zona que nunca se pintó.
2. **Líneas fantasma**: el "neck fill" de V2 (y 578–742) copiaba píxeles originales que incluían el contorno de la mandíbula; esa copia quedaba estática mientras la cabeza giraba.
3. **Collar roto**: el polígono de cabeza de V2 bajaba hasta y≈698 y atravesaba el collar (que empieza en y≈607 en el extremo izquierdo), así que parte del collar giraba con la cabeza.

## Cómo funciona

- **Campo de pesos** por articulación: 1 en la región rígida (cabeza), 0 en la región anclada (collar, cuerpo), transición continua en la banda intermedia (pelaje del cuello). La imagen se deforma como una sola pieza, así que no hay huecos ni costuras.
- **Inversión exacta**: para cada píxel de salida se resuelve qué píxel de origen le corresponde (pasos de punto fijo y luego Newton con jacobiano analítico).
- **Capa rígida superpuesta**: en el lado que se comprime, la cabeza se dibuja encima para que pueda tapar el collar en lugar de aplastarse.
- **Capas**: un rig puede repartir la imagen en capas (de atrás hacia delante). La cola de Daniela es una capa propia: así deja de estar pegada a la mejilla y queda lista para animarse más adelante. El reparto es exacto, de modo que la pose de reposo es idéntica al original píxel a píxel.
- **Movimiento**: pistas con fotogramas clave y curvas (`ease_in_out`, `ease_in_out_back` con sobrepaso suave, `hold`…) más una oscilación senoidal para la respiración.
- **Compositor**: coloca cada personaje una sola vez a partir de su caja en reposo, sin temblor, y envía los fotogramas a ffmpeg (H.264, yuv420p).

## Archivos

| Archivo | Función |
|---|---|
| `config/rigs/akira.json`, `config/rigs/daniela.json` | Polígonos, pivote y capas (coordenadas de `rig_prep_v1/*_master_padded.png`) |
| `config/animation/scenes/SC003_rig_pilot.json` | Encuadre y pistas del piloto SC003 |
| `scripts/render_rig_preview.py` | Depuración del rig: máscaras, campo de pesos, poses, zoom de costura y métricas |
| `scripts/render_scene_animation.py` | Render de escena: MP4, fotogramas clave, hoja de contactos y manifiesto |
| `tests/test_character_animation.py` | Tests sintéticos (funcionan en CI) y umbrales de calidad con los assets reales (se omiten si no están disponibles) |

```bash
python scripts/render_rig_preview.py --rig config/rigs/akira.json \
    --out projects/episode_001/character_rigs/akira/v3 --peak 12 --zoom 380 480 960 880
python scripts/render_scene_animation.py --spec config/animation/scenes/SC003_rig_pilot.json \
    --out projects/episode_001/animation/SC003/rig_pilot_v1
```

## Criterios de calidad automáticos

| Métrica | Umbral | Qué detecta |
|---|---|---|
| `rest_max_abs_error` | 0 | La pose de reposo altera el arte |
| `new_interior_holes_px` | ≤10 (Akira), ≤20 (Daniela) | Agujeros abiertos dentro de la silueta |
| `protected_max_abs_error` | <0.02 | La región anclada (collar o cuerpo) cambia |
| `head_stretch_max` | <3.5 (Akira), <2.0 (Daniela) | Estiramiento excesivo del pelaje en la banda |
| `max_abs_accel_per_frame2` | ~0.15 | Tirones en la animación |

Las métricas no sustituyen la revisión visual: cada cambio de rig se revisa con el zoom de costura y con fotogramas extraídos del MP4 codificado.

## Limitaciones conocidas

- **Arte maestro de Akira recortado**: la cola está cortada en vertical (x=0 del recorte) y el cuerpo en horizontal (abajo). En SC003 se oculta con el encuadre; las escenas que necesiten a Akira de cuerpo entero requieren arte nuevo.
- **Bigotes derechos de Daniela**: los trazos tenues que cruzan la cola se quedan en la capa de la cola, que es estática. Al inclinar la cabeza no siguen el movimiento; a escala de escena no se aprecia.
- **Extremo izquierdo del collar de Akira**: se dobla ligeramente con inclinaciones positivas. Es una decisión deliberada para evitar un pliegue del pelaje; el frente del collar y el medallón no se mueven.
- **Expresiones** (parpadeo, orejas, boca): requieren dibujos adicionales (por ejemplo, ojos cerrados); no se pueden obtener solo deformando la imagen.
- **Inclinación**: probada hasta +12°/−5° (Akira) y +10°/−4° (Daniela).
