# DEEPUTIN Forensic Workbench - Техническая документация

## Версии Pipeline

Проект содержит две версии forensic pipeline для анализа фотографий:

### run_pipeline_v1.py (Классическая версия)

**Особенности:**
- **Простая архитектура**: два режима работы - `extract` (извлечение признаков) и `matrix` (построение матрицы сравнений)
- **Попарное сравнение**: сравнивает все фото со всеми (N×N матрица)
- **Базовая калибровка**: использует статическую калибровку без учета позы
- **Однопроцессная обработка**: последовательная обработка без параллелизма
- **Простой CLI**: минимальные параметры запуска

**Использование:**
```bash
# Извлечение признаков
python run_pipeline_v1.py --mode extract --dataset /path/to/photos

# Построение матрицы сравнений
python run_pipeline_v1.py --mode matrix --dataset /path/to/photos
```

**Структура результатов:**
```
storage/
├── main/              # извлеченные данные
└── comparison_matrix.json  # матрица N×N сравнений
```

**Недостатки:**
- Квадратичная сложность O(N²) — медленно на больших датасетах
- Нет динамической калибровки по позе
- Нет хронологического анализа
- Нет детекции аномалий во времени

---

### run_pipeline_v2.py (SCAP - Sequential Calibration-Aware Pipeline)

**Особенности:**
- **Трехэтапная архитектура**: Extract → Calibrate → Analyze
- **Линейная сложность**: N-1 сравнений вместо N×N (в 800 раз быстрее на 1700 фото)
- **Группировка по ракурсам**: фото разделяются по yaw-углам (frontal, threequarter, profile и т.д.)
- **Хронологическая обработка**: сортировка по дате внутри каждой группы
- **Динамическая калибровка**: каждая пара калибруется через ближайшие калибровочные фото с похожей позой
- **EMA-статистика**: Exponential Moving Average для адаптивной калибровки
- **Reuse калибровки**: `cal_B` от предыдущей пары становится `cal_A` для следующей
- **Детекция аномалий**: автоматическое выявление скачков костных метрик и инверсий асимметрии
- **Ad-hoc режим**: сравнение любых двух фото (даже из разных ракурсов)
- **Параллельная обработка**: многопроцессорность для групп ракурсов

**Использование:**
```bash
# Полный pipeline (хронология всех фото)
python run_pipeline_v2.py --mode full

# Отдельные этапы
python run_pipeline_v2.py --mode extract
python run_pipeline_v2.py --mode calibrate --parallel
python run_pipeline_v2.py --mode analyze

# Ad-hoc сравнение двух конкретных файлов
python run_pipeline_v2.py --mode compare --photo_a photo1.jpg --photo_b photo2.jpg
```

**Структура результатов:**
```
storage/pipeline2/
├── pose/                          # основные фото с хронологией
│   ├── putin_2001_yaw15/
│   │   ├── photo_data.json        # метаданные, метрики зон, текстуры
│   │   ├── vertices.npy           # 3D модель
│   │   └── pair_with_next.json    # сравнение со следующим фото
│   ├── putin_2003_yaw18/
│   │   ├── photo_data.json
│   │   ├── vertices.npy
│   │   ├── pair_with_previous.json # сравнение с предыдущим
│   │   └── pair_with_next.json    # сравнение со следующим
│   └── chronology_index.json      # навигация: photo_id → [prev, next]
├── calibration/                   # калибровочные данные
│   └── cal_photo_yaw10/
│       ├── data.json
│       └── vertices.npy
└── comparisons/                   # ad-hoc сравнения
    └── photo1_photo2/
        └── comparison_report.json
```

**Ключевые улучшения:**
1. **Поза-зависимая калибровка**: шум от разного наклона головы устраняется автоматически
2. **Хронологическая непрерывность**: можно проследить эволюцию лица во времени
3. **Интерфейсная структура**: каждое фото имеет свою папку с данными и связями
4. **Ad-hoc гибкость**: сравнение любых двух фото вне хронологии
5. **Аномалии во времени**: детекция резких изменений (подмена личности, операции)

**Алгоритм калибровки:**
```
Фото_1 (yaw=15°)  →  Калибра_1 (yaw=15°)  = cal_A
Фото_2 (yaw=18°)  →  Калибра_2 (yaw=18°)  = cal_B

Разница cal_A - cal_B = естественный шум от наклона
Разница Фото_1 - Фото_2 - шум = истинное изменение лица
```

---

## Общее описание проекта

DEEPUTIN (Deep Putin Investigation) - это система криминалистического анализа фотографических портретов, предназначенная для выявления подмен личности и анализа хронологических изменений лица. Система рассматривает фотографии как археологические артефакты, несущие глубокую информацию о личности человека, и применяет передовые методы компьютерного зрения и машинного обучения для извлечения биометрических данных.

### Основные принципы работы

Система анализирует более 1700 фотографий за хронологию с 1999 по 2025 год, преобразуя плоские изображения в детальные 3D-модели лица с помощью нейросети 3DDFA_v3. Это позволяет получить точные координаты ключевых точек, форму костных структур и мягких тканей, а также текстурные характеристики кожи.

Ключевые особенности системы:
- Глубинная детекция истины по костным структурам (21 зона лица с анатомически обоснованными весами)
- Байесовский подход к судебно-медицинской экспертизе с множественными гипотезами
- Двигатель хронологических нарративов для выявления временных несоответствий
- Детектор синтетических материалов (силиконовые маски, дипфейки)
- Позракурсная судебно-медицинская экспертиза с зависимостью метрик от ракурса
- Система калибровки с самовосстанавливающейся базой данных
- Анализ, устойчивый к выражениям лица (динамическое исключение зон)

## Архитектура бекенда

Бекенд реализован на FastAPI и разделен на два основных модуля: `core/` и `pipeline/`.

### Структура директорий

```
backend/
├── main.py              # FastAPI приложение с API endpoints
├── core/                # Бизнес-логика и сервисы
│   ├── service.py       # ForensicWorkbenchService - основной сервис
│   ├── analysis.py      # Байесовский анализ и извлечение метрик
│   ├── calibration.py   # Система калибровки
│   ├── chronology.py    # Хронологический анализ
│   ├── compare.py       # Сравнение фотографий
│   ├── detail_mapper.py # Маппинг данных
│   ├── jobs.py          # Управление фоновыми задачами
│   ├── models.py        # Pydantic модели
│   ├── persona.py       # Управление персоналиями
│   ├── recommendations.py # Рекомендации по калибровке
│   ├── scoring.py       # Скоринг
│   ├── utils.py         # Утилиты
│   └── verdict.py       # Вердикты
└── pipeline/            # Обработка изображений и 3D реконструкция
    ├── reconstruction.py # 3D реконструкция через 3DDFA_v3
    ├── detect_pose.py   # Определение позы головы
    ├── zones.py         # Определение и анализ зон лица
    ├── scoring.py       # Вычисление метрик сходства
    ├── texture.py       # Текстурный анализ кожи
    ├── verdict.py       # Байесовские вердикты
    ├── alignment.py     # Выравнивание 3D моделей
    ├── calibration.py   # Калибровка pipeline
    ├── chronology.py    # Хронологический pipeline
    ├── cascade.py       # Каскадная обработка
    ├── compare.py       # Сравнение пар фотографий
    ├── quality_gate.py  # Контроль качества
    ├── visibility.py    # Определение видимости зон
    ├── uv_gen.py        # Генерация UV текстур
    └── types.py         # Типы данных
```

основной датасет фото для анализа лежит тут (в названиях файлов указана дата и углы наклона головы)
/Volumes/SDCARD/photo/all 

 тут лежит дататсет моих фотографий для калибровки (в названии тоже указаны углы наклона головы)
/Volumes/SDCARD/photo/calibration

Результаты извлекаться должны в эти папки /Volumes/SDCARD/storage/main и /Volumes/SDCARD/storage/calibration

## Основные модули core/

### service.py - ForensicWorkbenchService

Центральный сервис бекенда, который координирует все операции системы. Ключевые функции:

- **Управление датасетами**: Работа с двумя датасетами - main (основной анализ) и calibration (калибровочные данные)
- **Кэширование**: Интеллектуальное кэширование записей с TTL (30 секунд) для оптимизации производительности
- **Извлечение данных**: process_dataset() - обработка фотографий с извлечением 3D моделей и метрик
- **Сравнение**: compute_pairwise_matrix() - построение матрицы сходства N×N
- **Хронология**: get_timeline_full() - построение временной линии изменений
- **Калибровка**: calibration_summary() - статистика калибровочных данных
- **Рекомендации**: build_recommendations() - рекомендации по улучшению калибровки
- **Управление кэшем reconstruction**: load_reconstruction_cache() - загрузка кэшированных 3D моделей

### analysis.py - Байесовский анализ

В данном модуле реализована Байесовская логико-вероятностная модель нечеткого вывода для формирование итоговых результатов:

- **H0 (Same Person)**: Фотографии принадлежат одному и тому же человеку
- **H1 (Identity Swap)**: Подмена личности (маска, дипфейк)
- **H2 (Different Person)**: Разные люди

Ключевые функции:
- **extract_photo_bundle()**: Извлечение полного пакета данных для фотографии (3D модель, метрики, текстура)
- **calculate_bayesian_evidence()**: Вычисление байесовских доказательств для пары фотографий
- **recompute_metric_subset()**: Пересчет подмножества метрик

Веса зон (ZONE_WEIGHTS) определены анатомически:
- Костные структуры (вес 1.0): переносица, глазницы, челюсть, краниальный индекс
- Костно-связочные зоны (вес 0.8-0.9): подбородок, гониальные углы, кантальные углы
- Зоны симметрии (вес 0.7): асимметрия подбородка, индекс переносицы
- Мягкие ткани (вес 0.2-0.4): текстурные метрики, ширина носа, морщины

#### Байесовское Обновление Вероятностей

Система использует формулу Байеса для обновления априорных вероятностей с учетом полученных доказательств: P(H|E) = P(E|H) × P(H) / P(E). Каждое доказательство (геометрическое, текстурное, хронологическое) нормализуется и преобразуется в вероятность для каждой из трех гипотез. Затем байесовское обновление корректирует априорные вероятности: PRIOR_SAME_PERSON = 0.85, PRIOR_IDENTITY_SWAP = 0.05, PRIOR_DIFFERENT_PERSON = 0.10. Результатом является распределение вероятностей по всем трем гипотезам, которое позволяет системе определить наиболее вероятный сценарий и оценить степень уверенности в этом выводе.

### calibration.py - Система калибровки

Модуль отвечает за построение и поддержание калибровочной базы данных:

- **build_calibration_summary()**: Построение сводки калибровки по всем корзинам (buckets)
- **pose_distance()**: Вычисление расстояния между позами
- **stability_score()**: Оценка стабильности метрик
- **bucket_metric_health()**: Оценка здоровья метрик в конкретной корзине
- **get_epoch_noise_model()**: Получение шумовой модели для эпохи

Статусы метрик:
- **stable**: Робустный CV ≤ 0.12 или spread ≤ 0.015
- **marginal**: Робустный CV ≤ 0.24 или spread ≤ 0.03
- **replace**: Требуется замена калибровочных данных

### chronology.py - Хронологический анализ

Модуль выявляет хронологические несоответствия в последовательности фотографий:

- **build_timeline()**: Построение временной линии с кластеризацией метрик по группам (geometry, projection, texture)
- **build_timeline_summary()**: Сводка хронологических данных
- **_reference_medians()**: Вычисление референсных медиан для сравнения

Кластеры метрик для хронологического анализа:
- **geometry**: cranial_face_index, jaw_width_ratio, interorbital_ratio, orbital_asymmetry_index
- **projection**: nose_projection_ratio, chin_projection_ratio, orbit_depth ratios
- **texture**: texture_silicone_prob, texture_pore_density, wrinkle metrics

#### Ageing Curve (Кривая Старения)

Функция _reference_medians() вычисляет референсные медианы для каждого ракурса на основе фотографий до reference_year_end, создавая baseline для ожидаемых изменений. Кластеризация метрик по группам (geometry, projection, texture) позволяет строить плавную кривую старения, отражающую предсказуемые паттерны естественного старения: постепенное опущение мягких тканей, появление морщин, изменение формы подбородка. Система сравнивает текущие метрики с reference medians для выявления отклонений от нормального процесса старения.

#### Скачкообразные Изменения

Функция analyze_chronology() детектирует аномальные скачки метрик между соседними годами, проверяя delta > 0.15 для костной ширины (jaw_width_ratio). Severity классифицируется как danger (delta > 0.25) или warn (delta > 0.15). Система также выявляет инверсию асимметрии костей как биометрический маркер подмены личности. Скачкообразные изменения, которые не соответствуют естественному процессу старения (например, внезапное изменение формы носа или скул), могут указывать на пластическую операцию или манипуляцию изображением.

## Основные модули pipeline/

### reconstruction.py - 3D реконструкция

Модуль реализует 3D реконструкцию лица через нейросеть 3DDFA_v3:

Класс **ReconstructionAdapter**:
- Инициализация моделей 3DDFA_v3 с выбором устройства (CPU/GPU)
- Кэширование результатов реконструкции с защитой от OOM (Out Of Memory)
- MD5-хэширование для защиты кэша от ложной инвалидации
- Автоматическая очистка VRAM при достижении лимита кэша

Функции:
- **resolve_reconstruction()**: Разрешение реконструкции с кэшированием
- **load_reconstruction_cache()**: Загрузка кэшированной реконструкции
- **compute_image_hash()**: Вычисление MD5-хэша изображения

Кэш-ключ включает: путь к файлу, устройство, backbone, флаг нейтрального выражения

### detect_pose.py - Определение позы

Модуль определяет ориентацию головы в трехмерном пространстве:

Класс **PoseDetector**:
- Использует SCRFD детектор из библиотеки head-pose-estimation
- Вычисляет углы Эйлера: yaw (рыскание), pitch (тангаж), roll (крен)
- Классифицирует позу в одну из категорий: frontal, profile_left, profile_right, three_quarter_left, three_quarter_right
- Резервный механизм через 3DDFA_v3 если основной детектор не справился

Функции:
- **get_pose()**: Основная функция определения позы
- **_pose_from_3ddfa()**: Резервный механизм через 3DDFA
- **_canonical_yaw_deg()**: Канонизация угла yaw с учетом знака

Пороги классификации настраиваются через pose_settings.json

### zones.py - Зоны лица

Модуль определяет и анализирует 21 зону лица с анатомически обоснованными весами:

**Базовые зоны** (из 3DDFA-V3):
- right_eye, left_eye, right_eyebrow, left_eyebrow, nose, upper_lip, lower_lip, skin

**Производные зоны**:
- forehead, brow_ridge_L/R, orbit_L/R, nose_bridge_tip, nose_wing_L/R
- cheekbone_L/R, chin, jaw_L/R

Функции:
- **apply_expression_exclusion_mask()**: Динамическое исключение зон при мимике
- **filter_indices()**: Фильтрация индексов вершин (исключение ушей)
- **compute_zone_metrics()**: Вычисление метрик для каждой зоны

Пороги исключения:
- **THRESHOLD_JAW_OPEN = 0.22**: Открытие челюсти
- **THRESHOLD_SMILE = 2.2**: Улыбка

Исключаемые зоны при мимике: upper_lip, lower_lip, mouth, mouth_corners, cheeks, nose_wings

### scoring.py - Вычисление метрик сходства

Модуль вычисляет геометрические метрики для сравнения 3D моделей:

Функции:
- **score_aligned_pair()**: Основная функция скоринга выровненных пар
- **extract_macro_bone_metrics()**: Извлечение макро-костных метрик
- **compute_interorbital_ratio()**: Отношение межорбитального расстояния к скуловой ширине
- **fit_best_plane()**: Подбор наилучшей плоскости для точек
- **_robust_trimmed_3d_error()**: Робастная оценка ошибки с trimmed mean

Метрики:
- Истинное евклидово расстояние между выровненными вершинами (L2 норма)
- Нормализация к масштабу лица
- Взвешенное среднее с учетом надежности (reliability_weight)
- Trimmed mean для защиты от выбросов (TRIMMED_KEEP_RATIO = 0.8)

### texture.py - Текстурный анализ

Модуль анализирует текстуру кожи для детекции синтетических материалов:

Класс **SkinTextureAnalyzer**:
- LBP (Local Binary Pattern) анализ сложности текстуры
- GLCM (Gray-Level Co-occurrence Matrix) для контраста, энергии, гомогенности
- Gabor фильтры для анализа частотных характеристик
- Лапласиан для оценки резкости
- Анализ блеска (specular gloss)
- Оценка цвета кожи и пигментации

#### FFT Спектральный Анализ

Быстрое преобразование Фурье (FFT) применяется к патчам изображения для выявления периодичности в текстуре кожи. Естественная кожа имеет сложную, но хаотичную структуру пор и микрорельефа, тогда как синтетические материалы часто демонстрируют регулярные паттерны или аномальную гладкость. Алгоритм вычисляет спектральные характеристики и сравнивает их с эталонными значениями для настоящей кожи. Отклонения от нормального распределения частот указывают на возможное использование искусственного материала. FFT анализ - планируемая функциональность для будущих версий.

#### Анализ Цвета Альбедо и Жизнеспособности Кожи

Lab color features используются для анализа цвета кожи и оценки жизнеспособности:
- **skin_tone_std**: Стандартное отклонение светлости L канала Lab color space, отражающее вариативность пигментации кожи
- **pigmentation_index**: Стандартное отклонение канала a Lab color space, служащее индикатором жизнеспособности кожи

Естественная кожа имеет характерный спектр отражения, который зависит от пигментации, кровоснабжения и состояния эпидермиса. Силиконовые маски и другие синтетические материалы часто имеют неестественный цветовой баланс, который выявляется через статистический анализ Lab каналов. Индекс жизнеспособности кожи отражает то, насколько цветовые характеристики соответствуют живой ткани с нормальным кровоснабжением.

#### Детектор Синтетических Материалов

Функция compute_synthetic_probability() вычисляет вероятность наличия синтетических материалов на основе комбинации признаков: gloss_penalty (аномально высокие блики specular_gloss > 0.05), pore_penalty (идеально ровная текстура без пор pore_density < 50), uniformity_penalty (высокая монотонность пикселей lbp_uniformity > 0.15). Взвешенная сумма этих признаков дает вероятность от 0 до 1, которая усиливает гипотезу H1 (Identity Swap) при высоких значениях.

## Метрики по Ракурсам (BUCKET_METRIC_KEYS)

Система использует разный набор метрик для каждого ракурса в зависимости от видимости зон лица:

### frontal (Анфас) - 22 метрики

**Геометрические (14):**
- cranial_face_index: краниально-лицевой индекс
- jaw_width_ratio: отношение ширины челюсти
- canthal_tilt_L: наклон канта левого глаза
- canthal_tilt_R: наклон канта правого глаза
- chin_offset_asymmetry: асимметрия смещения подбородка
- nose_width_ratio: отношение ширины носа
- nose_projection_ratio: отношение проекции носа
- nasal_frontal_index: назальный фронтальный индекс
- nasofacial_angle_ratio: назофациальный угол
- chin_projection_ratio: отношение проекции подбородка
- gonial_angle_L: угол гониальной области слева
- gonial_angle_R: угол гониальной области справа
- orbital_asymmetry_index: индекс орбитальной асимметрии
- interorbital_ratio: межорбитальное отношение
- forehead_slope_index: индекс наклона лба
- orbit_depth_L_ratio: отношение глубины левой орбиты
- orbit_depth_R_ratio: отношение глубины правой орбиты

**Текстурные (8):**
- texture_silicone_prob: вероятность силикона
- texture_pore_density: плотность пор
- texture_spot_density: плотность пятен
- texture_wrinkle_forehead: морщины на лбу
- texture_wrinkle_nasolabial: носогубные морщины
- texture_global_smoothness: глобальная гладкость
- texture_specular_gloss: блеск
- texture_lbp_complexity: сложность LBP

### left_threequarter_light (Лёгкий поворот влево) - 21 метрика

**Геометрические (13):**
- cranial_face_index, forehead_slope_index, orbit_depth_L_ratio
- canthal_tilt_L, canthal_tilt_R, orbital_asymmetry_index, interorbital_ratio
- nose_projection_ratio, nasal_frontal_index, nose_width_ratio
- jaw_width_ratio, gonial_angle_L
- chin_projection_ratio, nasofacial_angle_ratio, chin_offset_asymmetry

**Текстурные (8):**
- texture_silicone_prob, texture_pore_density, texture_spot_density
- texture_wrinkle_forehead, texture_wrinkle_nasolabial, texture_global_smoothness
- texture_specular_gloss, texture_lbp_complexity

### right_threequarter_light (Лёгкий поворот вправо) - 21 метрика

**Геометрические (13):**
- cranial_face_index, forehead_slope_index, orbit_depth_R_ratio
- canthal_tilt_R, canthal_tilt_L, orbital_asymmetry_index, interorbital_ratio
- nose_projection_ratio, nasal_frontal_index, nose_width_ratio
- jaw_width_ratio, gonial_angle_R
- chin_projection_ratio, nasofacial_angle_ratio, chin_offset_asymmetry

**Текстурные (8):**
- texture_silicone_prob, texture_pore_density, texture_spot_density
- texture_wrinkle_forehead, texture_wrinkle_nasolabial, texture_global_smoothness
- texture_specular_gloss, texture_lbp_complexity

### left_threequarter_mid (Левые 3/4 средние) - 18 метрик

**Геометрические (10):**
- cranial_face_index, forehead_slope_index, orbit_depth_L_ratio, canthal_tilt_L
- orbital_asymmetry_index, interorbital_ratio
- nose_projection_ratio, nasal_frontal_index, nasofacial_angle_ratio
- jaw_width_ratio, gonial_angle_L
- chin_projection_ratio, chin_offset_asymmetry

**Текстурные (8):**
- texture_silicone_prob, texture_pore_density, texture_spot_density
- texture_wrinkle_forehead, texture_wrinkle_nasolabial, texture_global_smoothness
- texture_specular_gloss, texture_lbp_complexity

### right_threequarter_mid (Правые 3/4 средние) - 18 метрик

**Геометрические (10):**
- cranial_face_index, forehead_slope_index, orbit_depth_R_ratio, canthal_tilt_R
- orbital_asymmetry_index, interorbital_ratio
- nose_projection_ratio, nasal_frontal_index, nasofacial_angle_ratio
- jaw_width_ratio, gonial_angle_R
- chin_projection_ratio, chin_offset_asymmetry

**Текстурные (8):**
- texture_silicone_prob, texture_pore_density, texture_spot_density
- texture_wrinkle_forehead, texture_wrinkle_nasolabial, texture_global_smoothness
- texture_specular_gloss, texture_lbp_complexity

### left_threequarter_deep (Левые 3/4 глубокие) - 17 метрик

**Геометрические (9):**
- cranial_face_index, forehead_slope_index, orbit_depth_L_ratio, canthal_tilt_L
- nose_projection_ratio, nasofacial_angle_ratio
- jaw_width_ratio, gonial_angle_L
- chin_projection_ratio, chin_offset_asymmetry, orbital_asymmetry_index

**Текстурные (8):**
- texture_silicone_prob, texture_pore_density, texture_spot_density
- texture_wrinkle_forehead, texture_wrinkle_nasolabial, texture_global_smoothness
- texture_specular_gloss, texture_lbp_complexity

### right_threequarter_deep (Правые 3/4 глубокие) - 17 метрик

**Геометрические (9):**
- cranial_face_index, forehead_slope_index, orbit_depth_R_ratio, canthal_tilt_R
- nose_projection_ratio, nasofacial_angle_ratio
- jaw_width_ratio, gonial_angle_R
- chin_projection_ratio, chin_offset_asymmetry, orbital_asymmetry_index

**Текстурные (8):**
- texture_silicone_prob, texture_pore_density, texture_spot_density
- texture_wrinkle_forehead, texture_wrinkle_nasolabial, texture_global_smoothness
- texture_specular_gloss, texture_lbp_complexity

### left_profile (Левый профиль) - 19 метрик

**Геометрические (11):**
- cranial_face_index, forehead_slope_index, orbit_depth_L_ratio, canthal_tilt_L
- nose_projection_ratio, nasal_frontal_index, nose_width_ratio, nasofacial_angle_ratio
- jaw_width_ratio, gonial_angle_L, mandibular_ramus_length (длина ветви нижней челюсти)
- chin_projection_ratio, chin_offset_asymmetry

**Текстурные (8):**
- texture_silicone_prob, texture_pore_density, texture_spot_density
- texture_wrinkle_forehead, texture_wrinkle_nasolabial, texture_global_smoothness
- texture_specular_gloss, texture_lbp_complexity

### right_profile (Правый профиль) - 19 метрик

**Геометрические (11):**
- cranial_face_index, forehead_slope_index, orbit_depth_R_ratio, canthal_tilt_R
- nose_projection_ratio, nasal_frontal_index, nose_width_ratio, nasofacial_angle_ratio
- jaw_width_ratio, gonial_angle_R, mandibular_ramus_length (длина ветви нижней челюсти)
- chin_projection_ratio, chin_offset_asymmetry

**Текстурные (8):**
- texture_silicone_prob, texture_pore_density, texture_spot_density
- texture_wrinkle_forehead, texture_wrinkle_nasolabial, texture_global_smoothness
- texture_specular_gloss, texture_lbp_complexity

### unclassified (Не классифицировано) - 17 метрик

**Геометрические (9):**
- cranial_face_index, forehead_slope_index, jaw_width_ratio
- gonial_angle_L, gonial_angle_R, interorbital_ratio, orbital_asymmetry_index
- orbit_depth_L_ratio, orbit_depth_R_ratio, nose_width_ratio, nose_projection_ratio
- nasal_frontal_index, nasofacial_angle_ratio, chin_projection_ratio, chin_offset_asymmetry

**Текстурные (8):**
- texture_silicone_prob, texture_pore_density, texture_spot_density
- texture_global_smoothness, texture_specular_gloss, texture_lbp_complexity

### FORENSIC_RADAR_AXES - Оси для Radar Chart

**Cranial**: cranial_face_index, forehead_slope_index
**Orbital**: orbit_depth_L_ratio, orbit_depth_R_ratio, canthal_tilt_L, canthal_tilt_R
**Mandibular**: jaw_width_ratio, gonial_angle_L, gonial_angle_R
**Nasal**: nose_width_ratio, nose_projection_ratio, nasal_frontal_index
**Symmetry**: chin_offset_asymmetry, orbital_asymmetry_index
**Texture**: texture_pore_density, texture_lbp_complexity
**Material**: texture_silicone_prob, texture_specular_gloss
**Stability**: reliability_weight

### Классификация ракурсов (classify_pose_bucket)

Пороги yaw (градусы):
- **frontal**: |yaw| ≤ 12°
- **threequarter_light**: 12° < |yaw| ≤ 25°
- **threequarter_mid**: 25° < |yaw| ≤ 45°
- **threequarter_deep**: 45° < |yaw| ≤ 65°
- **profile**: |yaw| > 65°

Направление определяется знаком yaw (положительный = вправо, отрицательный = влево)

## Сравнение и Выравнивание Фотографий внутри Ракурсов

### Канонизация Позы (Canonical Pose Normalization)

Функция **canonicalize_vertices_for_bucket()** в alignment.py:
- Приводит 3D-меш к канонической системе координат бакета
- Нейтрализует наклон (pitch), крен (roll) и доводит поворот (yaw) до идеала
- Использует _CANONICAL_YAW_BY_VIEW_GROUP для каждого ракурса:
  - frontal: 0.0°
  - left_threequarter_light: -22.5°
  - right_threequarter_light: 22.5°
  - left_threequarter_mid: -45.0°
  - right_threequarter_mid: 45.0°
  - left_threequarter_deep: -67.5°
  - right_threequarter_deep: 67.5°
  - left_profile: -90.0°
  - right_profile: 90.0°

Алгоритм канонизации:
1. Строит матрицу ТЕКУЩЕГО поворота из angles_deg (3DDFA формат: [pitch, yaw, roll])
2. Строит матрицу ЦЕЛЕВОГО поворота (Pitch и Roll жестко равны нулю, Yaw = канонический)
3. Вычисляет компенсирующую дельта-матрицу: R_align = R_current.T @ R_target
4. Вращает меш строго вокруг его центроида для избежания смещения
5. Применяет трансформацию: aligned_vertices = (vertices - centroid) @ R_align + centroid

### Выравнивание Пары (Pair Alignment)

Функция **align_canonical_pair_for_view_group()**:
- Выравнивает пару лиц к каноническому позу для view_group
- Использует среднее pitch и roll пары для лучшей стабильности
- Определяет target_yaw из _CANONICAL_YAW_BY_VIEW_GROUP
- Вычисляет матрицы вращения для текущих поз: R_a, R_b
- Вычисляет матрицу целевой позы: R_target
- Alignment rotations: R_align_a = R_a.T @ R_target, R_align_b = R_b.T @ R_target
- Центрирует и выравнивает: va_canon = (vertices_a - translation_a) @ R_align_a
- Применяет финальное жесткое выравнивание через rigid_umeyama с allow_scale=True

### Метод Umeyama (Rigid Umeyama Alignment)

Функция **rigid_umeyama()**:
- Взвешенное жесткое выравнивание по методу Umeyama
- Вход: source, target (N,3), weights (опционально), allow_scale
- Центрирует с учетом весов: source_mean = sum(source * w) / sum(w)
- Вычисляет матрицу ковариации: m = (centered_source * w).T @ centered_target
- Защита от вырожденности: проверка rank(m) < 3
- SVD разложение: u, s, vh = np.linalg.svd(m)
- Вычисляет rotation с защитой от отражения: sign_matrix = diag([1, 1, sign(det(u @ vh))])
- rotation = u @ sign_matrix @ vh
- scale вычисляется только если allow=True: scale = (s[0] + s[1] + s[2] * sign(d)) / var_source
- translation = target_mean - scale * (source_mean @ rotation)
- Возвращает AlignmentResult с rotation, translation, scale, residual_before/after

Функция **rigid_umeyama_robust()**:
- Исправленная версия с защитой от сингулярности SVD
- Защита от двойного масштабирования
- Проверка rank(H) < 3 с выбросом исключения
- Расчет масштаба только один раз: scale = sum(S) / (src_var + 1e-10)
- Защита от отражения: if det(R) < 0: Vt[2, :] *= -1

### Скоринг Выровненной Пары

Функция **score_aligned_pair()**:
- Вычисляет истинное евклидово расстояние между выровненными вершинами (L2 норма)
- Оценивает масштаб лица через percentiles (95%, 5%) по X и Y
- FACE_SCALE_Y_FACTOR для профилей: scale = max(x_extent, y_extent * 1.2)
- Нормализует расстояния к масштабу лица: distances_normalized = true_distances / scale_b
- Применяет reliability_weight из текстуры/позы
- Вычисляет primary_error через weighted_mean_abs
- Вычисляет robust_error через _robust_trimmed_3d_error с TRIMMED_KEEP_RATIO = 0.8
- Возвращает primary_error, bounded_score, robust_error, bounded_robust, plane_normal

Функция **_robust_trimmed_3d_error()**:
- Робастная trimmed mean с защитой MIN_KEEP_N
- Если n <= MIN_KEEP_N: возвращает weighted_mean_abs
- Вычисляет n_keep = max(int(n * keep_ratio), min_keep_n)
- Находит cutoff через partition
- Фильтрует значения <= cutoff
- Возвращает weighted_mean_abs от отфильтрованных значений

### Обобщенный Прокрустов Анализ (GPA)

Функция **align_and_score_gpa()**:
- GPA только по валидным (shared) костным ориентирам через mask
- Вызывает rigid_umeyama_robust с allow_scale=True
- Применяет трансформацию ко ВСЕМ вершинам A
- Вычисляет raw_errors в правильном метрическом пространстве
- Возвращает verts_a_aligned, raw_errors

## Механизм Исключения Шумов от Разного Наклона Головы

### Калибровка по Ракурсам (Pose-Based Calibration)

Функция **build_calibration_summary()**:
- Строит статистику по всем корзинам (buckets) отдельно
- Фильтрует некачественные записи (overall_score < 0.35, QUALITY_REJECTED_TEXTURE)
- Для каждой метрики в каждом бакете вычисляет:
  - median (медиана значений)
  - mad (Median Absolute Deviation)
  - robust_cv = mad / abs(median) (коэффициент вариации)
  - status: stable (robust_cv ≤ 0.12), marginal (≤ 0.24), replace (> 0.24)
- Выбирает best_reference по минимальному pose_score + quality_penalty
- Возвращает calibration_summary с buckets, metrics, observation_count

### Допустимая Дельта Метрики

Функция **allowed_metric_delta()**:
- Вычисляет допустимую вариативность метрики для данного бакета и days_delta
- Базовый delta = max(spread * 3.0, 0.018) для геометрии
- Для текстуры: base = max(spread * 3.0, 0.04)
- Модификаторы статуса:
  - stable: base * 0.9
  - marginal: base (без изменения)
  - replace: base * 1.4
- Временные модификаторы:
  - days_delta < 14: base * 0.75
  - days_delta < 30: base * 0.85
  - days_delta > 365: base * 1.2
  - days_delta > 3650: base * 1.5

### Поиск Калибровочной Пары

Функция **find_calibration_match()**:
- Ищет запись в калибровочной базе с близкими углами и эпохой
- Параметры: max_pose_distance = 10.0°, max_year_gap = 3 года
- pose_distance = sqrt(yaw² + pitch² + roll²)
- Комбинированный score = pose_dist * 0.7 + year_gap * 2.0
- Штраф за низкое качество: +10.0 если overall_score < 0.5
- Возвращает лучшую калибровочную запись или None

### Шумовая Модель Эпохи (Epoch Noise Model)

Функция **get_epoch_noise_model()**:
- Разные эпохи фото имеют разный уровень шума:
  - < 2005 (аналоговая): geometric_sigma_multiplier = 1.4, texture_threshold_boost = 0.08, confidence_penalty = 0.15
  - 2005-2010 (переходный): 1.2, 0.04, 0.08
  - 2010-2015 (ранняя цифра): 1.1, 0.02, 0.04
  - 2015+ (современная): 1.0, 0.0, 0.0
- Старые фото имеют больше допустимой вариативности геометрии
- Снижается порог детекции синтетики для старых фото (больше шума = сложнее найти силикон)
- Confidence penalty снижает уверенность для старых фото

### Калибровочный Likelihood

Функция **compute_calibration_informed_likelihood()**:
- Вычисляет правдоподобие с учетом калибровки
- Проверяет MIN_OBSERVATIONS = 3: если меньше, возвращает нейтральный likelihood = 0.5
- Получает allowed_delta из allowed_metric_delta()
- Применяет epoch_model multiplier: allowed_delta *= geometric_sigma_multiplier
- Вычисляет ratio = delta / allowed_delta
- Likelihood = exp(-ratio² * 0.5) * status_penalty
- Status penalty: stable = 1.0, marginal = 0.7, replace = 0.4
- Применяет confidence_penalty эпохи: likelihood *= (1.0 - confidence_penalty)
- Возвращает likelihood (0-1) и metadata с деталями

### Исключение Зон при Мимике

Функция **apply_expression_exclusion_mask()**:
- Удаляет зоны, искаженные мимикой
- Проверяет smile_intensity из expression_params[0]
- Если smile_intensity > 2.2:
  - nose_width_ratio = np.nan
  - jaw_width_ratio = np.nan
- Использует np.nan вместо None для безопасности матричных вычислений

Функция **calculate_coverage()**:
- Считает реальное покрытие метрик после исключений
- Если метрика = np.nan, она снижает покрытие
- Coverage = valid_count / len(expected_keys)

### Маскировка Окклюзированных Зон

В extract_macro_bone_metrics() (scoring.py):
- Mask unreliable canthal tilt & orbit depth на окклюзированной стороне для non-frontal (yaw > 20°)
- Если yaw < 0 (левый профиль): правая сторона окклюзирована
  - canthal_tilt_R = None
  - orbit_depth_R_ratio = None
- Если yaw > 0 (правый профиль): левая сторона окклюзирована
  - canthal_tilt_L = None
  - orbit_depth_L_ratio = None

- Pitch guard: при наклоне головы > 20° подбородок геометрически недостоверен для фронтальных ракурсов (|yaw| ≤ 30°)
  - chin_projection_ratio = None
  - gnathion_midline_deviation_ratio = None
  - chin_offset_asymmetry = None

### Reliability Weight

В extract_macro_bone_metrics():
- Вычисляет reliability на основе углов позы:
  - base = 1.0
  - if yaw_abs > 30: reliability *= 0.5
  - if pitch_abs > 20: reliability *= 0.7
- Используется в score_aligned_pair() для взвешивания ошибок
- effective_weights = weights * reliability_weight

### Динамическое Исключение Зон

В zones.py:
- apply_expression_exclusion_mask() динамически исключает зоны при мимике
- THRESHOLD_JAW_OPEN = 0.22: открытие челюсти
- THRESHOLD_SMILE = 2.2: улыбка
- Исключаемые зоны при улыбке: upper_lip, lower_lip, mouth, mouth_corners, cheeks, nose_wings

### Visibility Mask

В visibility.py:
- compute_software_zbuffer_mask() детектирует окклюзию через Z-буфер
- Grid 256x256 для вычисления минимальной глубины
- Z_TOLERANCE_RATIO = 0.005 от диапазона глубин
- compute_visibility() комбинирует normal-based проверку и Z-буфер
- Gradient fade для yaw 45-60°: плавное затухание весов для предотвращения "галлюцинаций"
- Возвращает VisibilityResult с binary_mask и cosine_weights

### Интеграция Механизмов

Полный пайплайн исключения шумов:
1. **Канонизация позы**: приведение к идеальному yaw для ракурса
2. **Калибровка по бакету**: статистика вариативности для каждого ракурса отдельно
3. **Epoch noise model**: учет эпохи съемки для допустимой вариативности
4. **Allowed delta**: динамический порог на основе калибровки и времени
5. **Calibration likelihood**: экспоненциальное затухание likelihood от delta/allowed
6. **Expression exclusion**: динамическое исключение зон при мимике
7. **Occlusion masking**: маскировка окклюзированных зон по yaw
8. **Reliability weight**: снижение веса при экстремальных углах
9. **Robust statistics**: trimmed mean, median, MAD для защиты от выбросов
10. **Visibility mask**: Z-буфер для детекции окклюзии с gradient fade

Группы метрик:
- **UNIVERSAL**: lbp_uniformity, glcm_contrast, gabor_mean, laplacian_energy, spot_density, specular_gloss
- **CONDITIONAL**: wrinkle_forehead, nasolabial_depth, crow_feet_score, nose_pore_density
- **UV ZONE**: uv_spot_density, uv_wrinkle_energy, uv_silicone_flatness, uv_retouch_score
- **QUALITY**: quality_sharpness_score, quality_noise_score, quality_index

ROI (Region of Interest) определяется в зависимости от угла yaw для анализа соответствующих зон лица

### verdict.py - Байесовские вердикты

Модуль реализует байесовский механизм принятия решений:

Классы:
- **ForensicStatus**: SAME_PERSON, UNCERTAIN, DIFFERENT_PERSON, IDENTITY_SWAP, RETURN_TO_BASELINE
- **GeometryEvidenceMode**: CALIBRATED, FALLBACK, UNAVAILABLE
- **FuzzyLabel**: STRONGLY_MATCHING, CONSISTENT, INSUFFICIENT_DATA, WEAK_EVIDENCE, SUSPICIOUS_TEXTURE, GEOMETRIC_MISMATCH, IDENTITY_ANOMALY, TEMPORAL_IMPOSSIBILITY
- **ForensicVerdict**: Основной класс вердикта с вероятностями H0/H1/H2, уверенностью, флагами и рассуждениями

Функции:
- **compute_forensic_verdict()**: Вычисление криминалистического вердикта
- **_update_posteriors_log_domain()**: Обновление апостериорных вероятностей в логарифмической области (Log-Sum-Exp trick)
- **_attenuate_likelihood()**: Ослабление likelihood для учета неопределенности

Константы из core/constants:
- PRIOR_SAME_PERSON: априорная вероятность H0
- PRIOR_IDENTITY_SWAP: априорная вероятность H1
- SNR_SIGNAL_THRESHOLD: порог отношения сигнал/шум
- CHRONO_FLAG_IMPOSSIBLE: флаг временной невозможности

## API Endpoints (main.py)

FastAPI приложение предоставляет следующие основные endpoints:

### Управление фотографиями
- **GET /api/photos/{dataset}**: Список фотографий с фильтрацией по pose, source, search, sortBy
- **GET /api/photo/{dataset}/{photo_id}**: Детальная информация о фотографии
- **POST /api/upload**: Загрузка новой фотографии
- **DELETE /api/photo/{dataset}/{photo_id}**: Удаление производных данных

### Сравнение и анализ
- **POST /api/evidence/compare**: Сравнение двух фотографий с байесовским анализом
- **POST /api/evidence/matrix**: Матрица сходства N×N для выбранных фотографий
- **GET /api/similar-photos/{photo_id}**: Поиск похожих фотографий

### Хронология и калибровка
- **GET /api/timeline-summary**: Сводка хронологических данных
- **GET /api/calibration/summary**: Статистика калибровки
- **GET /api/recommendations**: Рекомендации по улучшению калибровки

### 3D модели
- **GET /api/mesh/{dataset}/{photo_id}**: Данные 3D сетки (vertices, UVs, triangles, normals)

### Фоновые задачи
- **GET /api/jobs**: Список задач
- **POST /api/jobs/extract**: Запуск извлечения данных
- **POST /api/jobs/recompute-metrics**: Пересчет метрик

### Диагностика и отладка
- **GET /api/health**: Проверка здоровья системы
- **GET /api/overview**: Общая статистика
- **GET /api/pipeline/stages**: Диагностика стадий пайплайна
- **GET /api/anomalies**: Список криминалистических аномалий
- **GET /api/diary**: Дневник расследований

### Управление системой
- **POST /api/reset-all**: Полный сброс системы
- **POST /api/extract/upload**: Загрузка фото для временного сравнения

## Запуск системы

### CLI режим (run_pipeline.py)

```bash
python run_pipeline.py --mode extract --dataset /path/to/photos --case_name case_name
python run_pipeline.py --mode matrix --dataset /path/to/photos --case_name case_name
```

Режимы:
- **extract**: Offline Extraction - извлечение сырых данных 1 раз для каждого фото
- **matrix**: Online Inference - сравнение N×N с готовыми JSON (без GPU и 3DDFA)

### Server режим (main.py)

```bash
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8011
```

Сервер автоматически запускает localxpose туннель если настроен токен в SETTINGS.localxpose_token

## Дополнительные модули pipeline/

### alignment.py - Выравнивание 3D моделей

Модуль реализует взвешенное жесткое выравнивание по методу Umeyama:

Функция **rigid_umeyama()**:
- Вычисляет матрицу вращения, масштаб и трансляцию для выравнивания source к target
- Поддерживает взвешивание точек (weights) для приоритизации костных зон
- Защита от вырожденных случаев: проверка ранга матрицы ковариации, сумма весов > 1e-8
- Возвращает AlignmentResult с rotation (3x3), translation (3,), scale, residual_before/after

Канонические углы yaw по группам видов:
- frontal: 0.0°, left_profile: -90.0°, right_profile: 90.0°
- three_quarter_light: ±22.5°, three_quarter_mid: ±45.0°, three_quarter_deep: ±67.5°

### quality_gate.py - Контроль качества

Класс **QualityGate** обеспечивает фильтрацию изображений по техническому качеству:

Параметры:
- blur_threshold: порог размытия (Laplacian variance)
- noise_threshold: порог шума

Функция **evaluate()**:
- Проверка читаемости файла (INSUFFICIENT_DATA_UNREADABLE при ошибке)
- Проверка минимального разрешения лица (FACE_TOO_SMALL если < 150px)
- Оценка резкости через вариацию Лапласиана (sharpness_score = blur_score / 150.0)
- Оценка шума через median blur (noise_quality = 1.0 - noise_score / 25.0)
- Итоговый score: 0.7 * sharpness_score + 0.3 * noise_quality

Флаги rejection:
- QUALITY_REJECTED_TEXTURE: текстура непригодна для форензики
- FACE_TOO_SMALL: лицо слишком мелкое
- INSUFFICIENT_DATA_UNREADABLE: файл не читается

### visibility.py - Видимость зон

Модуль определяет видимость вершин 3D модели с учетом окклюзии:

Функция **compute_software_zbuffer_mask()**:
- Программный Z-буфер для детекции окклюзии
- Разбивает пространство на grid 256x256
- Вычисляет минимальную глубину для каждой ячейки
- Тolerance: Z_TOLERANCE_RATIO = 0.005 от диапазона глубин
- Возвращает булеву маску видимых вершин

Функция **compute_visibility()**:
- Комбинирует нормальный-based проверку (facing angle) и Z-буфер
- Порог угла: angle_threshold_deg (обычно 75-80°)
- Gradient fade для yaw 45-60°: плавное затухание весов для предотвращения "галлюцинаций" в профильных снимках
- Возвращает VisibilityResult с binary_mask и cosine_weights

### compare.py - Сравнение пар

Класс **InvestigationEngine** для офлайн сравнения фотографий:

Функции:
- **_load_all_summaries()**: Загружает все summary.json в оперативную память (Offline Store)
- **compute_n_x_n_matrix()**: Мгновенное вычисление матрицы сходства N×N без нейросетей
- **suspicious_windows()**: Поиск подозрительных интервалов аномалий (H0 < 0.4)
- **_compute_bayesian_evidence()**: Обертка над calculate_bayesian_evidence() из analysis.py

Оптимизации:
- Вычисление только верхнего треугольника матрицы (symmetric)
- Защита от KeyError при сериализации (использует metric_key вместо metric)
- Возвращает np.nan для пар с ошибками

### cascade.py - Каскадная обработка

Модуль организует многоступенчатую обработку с fallback механизмами:

Стадии каскада:
1. Pose Detection → fallback к 3DDFA при неудаче
2. Reconstruction → кэширование с защитой от OOM
3. Quality Gate → soft rejection вместо crash
4. Metric Extraction → пересчет при изменении констант

Каждая стадия возвращает статус (success/failure) и fallback_reason

### calibration.py (pipeline) - Калибровка pipeline

Модуль калибровки для pipeline-level операций:

- **build_noise_model()**: Построение шумовой модели по корзинам
- **find_calibration_match()**: Поиск лучшего калибровочного фото по pose distance
- **compute_calibration_informed_likelihood()**: Вычисление likelihood с учетом калибровки

Использует pose_distance() из core/calibration.py

### chronology.py (pipeline) - Хронологический pipeline

Модуль для хронологического анализа на уровне pipeline:

- **compute_ageing_curve()**: Построение кривой старения по метрикам
- **detect_chronological_anomalies()**: Детекция аномалий во временной линии
- **compute_temporal_delta()**: Вычисление дельты между соседними фото

Интегрируется с core/chronology.py для бизнес-логики

### uv_gen.py - Генерация UV текстур

Модуль генерации UV-разверток для текстурного анализа:

- **generate_uv_texture()**: Создание UV текстуры из 3D модели
- **extract_uv_patches()**: Извлечение патчей текстуры для анализа
- **compute_uv_metrics()**: Вычисление UV-специфичных метрик

Интеграция с uv_module/hd_uv_generator.py (опционально)

### types.py - Типы данных

Модуль определяет типы данных для pipeline:

Классы:
- **ReconstructionResult**: vertices, normals, uv_coords, triangles, angles_deg, exp_params
- **AlignmentResult**: rotation (3x3), translation (3,), scale, residual_before/after
- **ZoneMetric**: zone_name, value, weight, reliability
- **VisibilityResult**: binary_mask, cosine_weights, visible_count
- **TextureMetrics**: 4 группы метрик (UNIVERSAL, CONDITIONAL, UV ZONE, QUALITY)

## Дополнительные модули core/

### compare.py - Офлайн сравнение

Класс **InvestigationEngine** (описан выше в pipeline/compare.py):

Загружает все summary.json в память и вычисляет матрицу N×N мгновенно через простые арифметические операции без GPU.

### detail_mapper.py - Маппинг данных

Модуль преобразует внутренние данные в стандартизированный формат:

Функция **map_record_to_detail()**:
- Преобразует record из storage в стандартизированный формат
- Раскрывает nested структуры (pose, metrics, artifacts)
- Добавляет вычисляемые поля (zone_summary, texture_summary)
- Форматирует даты и числовые значения

### jobs.py - Управление фоновыми задачами

Класс **JobManager** для асинхронного выполнения долгих операций:

Класс **JobRecord**:
- Поля: job_id, job_type, dataset, status, progress, total, completed, message, errors, timestamps
- Метод as_dict(): сериализация в JSON

Класс **JobManager**:
- **start()**: Запуск новой задачи с progress_callback
- **list_jobs()**: Список всех задач
- **get()**: Детали задачи по job_id
- **_update()**: Внутреннее обновление статуса (thread-safe через lock)

Типы задач: extract, recompute-metrics

### models.py - Pydantic модели

Модуль определяет Pydantic модели для валидации данных:

Классы:
- **ExtractJobRequest**: dataset, limit, only_ids
- **RecomputeMetricsRequest**: dataset, metric_keys, only_ids
- **CalibrationOverrideRequest**: photo_id, calibration_photo_id, reason, author

Используются в API endpoints для валидации входных данных

### persona.py - Управление персоналиями

Модуль для управления персоналиями (наборами фотографий одного человека):

- **create_persona()**: Создание новой персоналии
- **add_photo_to_persona()**: Добавление фото в персоналию
- **list_personas()**: Список всех персоналий
- **compute_persona_consistency()**: Вычисление внутренней согласованности персоналии

### recommendations.py - Рекомендации по калибровке

Функция **build_recommendations()**:

Анализирует calibration_summary и генерирует рекомендации:
- Недостающие корзины (white zones)
- Корзины с low confidence
- Метрики со статусом "replace"
- Предлагает конкретные фото для добавления в калибровку

### scoring.py (core) - Скоринг на уровне core

Модуль агрегирует скоринг из разных источников:

- **aggregate_zone_scores()**: Агрегация оценок по зонам с весами
- **compute_overall_score()**: Общий скоринг из geometry и texture
- **apply_reliability_weight()**: Применение веса надежности

### utils.py - Утилиты

Модуль общих утилит:

Константы:
- **ALL_BUCKETS**: Список всех корзин поз
- **BUCKET_LABELS**: Человеко-читаемые названия корзин
- **BUCKET_METRIC_KEYS**: Метрики для каждой корзины
- **FORENSIC_RADAR_AXES**: Оси для radar chart

Функции:
- **stable_photo_id()**: Генерация стабильного ID от пути
- **parse_date_from_name()**: Парсинг даты из имени файла
- **fallback_date_for_file()**: Fallback даты из mtime
- **read_json() / write_json()**: Чтение/запись JSON с обработкой ошибок
- **ensure_directory()**: Создание директории с parents=True
- **bytes_to_human()**: Конвертация байт в человеко-читаемый формат
- **directory_size()**: Размер директории рекурсивно
- **median() / mad()**: Робастная медиана и MAD
- **clamp()**: Ограничение значения в диапазоне

### verdict.py (core) - Вердикты на уровне core

Модуль бизнес-логики для вердиктов:

- **format_verdict()**: Форматирование вердикта
- **explain_verdict()**: Генерация текстового объяснения
- **aggregate_flags()**: Агрегация флагов аномалий

## Конфигурация и константы

### core/config.py - Конфигурация

Класс **SETTINGS** (singleton):
- **newapp_root**: Корневая директория проекта
- **storage_root**: Директория для хранения артефактов
- **main_photos_dir**: Директория основных фотографий
- **calibration_dir**: Директория калибровочных фотографий
- **port**: Порт сервера (8011)
- **localxpose_token**: Токен для туннеля (опционально)
- **reference_year_end**: Конец референсного периода для хронологии

### core/constants.py - Константы системы

Пороги и параметры:
- **ALIGNMENT_MIN_RANK**: Минимальный ранг для выравнивания
- **MIN_ZONE_VERTICES**: Минимальное количество вершин в зоне
- **TRIMMED_KEEP_RATIO**: Доля сохраняемых значений при trimmed mean (0.8)
- **MIN_KEEP_N**: Минимальное количество значений при trimmed mean
- **FACE_SCALE_Y_FACTOR**: Фактор масштаба по Y для профилей
- **Z_TOLERANCE_RATIO**: Тolerance для Z-буфера (0.005)

Априорные вероятности:
- **PRIOR_SAME_PERSON**: 0.85
- **PRIOR_IDENTITY_SWAP**: 0.05
- **PRIOR_DIFFERENT_PERSON**: 0.10

Пороги SNR:
- **SNR_SIGNAL_THRESHOLD**: 3.0
- **SNR_UNCERTAIN_THRESHOLD**: 1.5

Флаги хронологии:
- **CHRONO_FLAG_IMPOSSIBLE**: временная невозможность
- **CHRONO_FLAG_RETURN**: возврат к baseline
- **CHRONO_FLAG_TRANSITION**: переход между состояниями

### pipeline/constants.py - Константы pipeline

- **BLUR_THRESHOLD_DEFAULT**: Порог размытия (100.0)
- **NOISE_THRESHOLD_DEFAULT**: Порог шума (25.0)

## Структура данных и storage

### Директории storage/

```
storage/
├── main/                    # Основной датасет
│   ├── {photo_id}/
│   │   ├── summary.json     # Основные данные
│   │   ├── metrics.json     # Метрики
│   │   ├── texture.json     # Текстурные данные
│   │   ├── pose.json        # Данные позы
│   │   ├── reconstruction_v1.pkl  # Кэш 3D модели
│   │   ├── uv_texture.png  # UV текстура
│   │   └── artifacts/       # Дополнительные артефакты
├── calibration/             # Калибровочный датасет
│   └── {photo_id}/          # Аналогичная структура
├── temp/                    # Временные фото для сравнения
│   └── temp_{uuid}/
├── poses/                   # Отчеты о позах
│   ├── poses_main.json
│   └── poses_myface.json
├── duplicate-clusters.json  # Кластеры дубликатов
├── calibration_overrides.json # Переопределения калибровки
└── investigations.json      # Расследования
```

### Формат summary.json

Основной файл данных для каждой фотографии:

```json
{
  "photo_id": "уникальный ID",
  "filename": "имя файла",
  "dataset": "main|calibration",
  "bucket": "frontal|profile_left|...",
  "date_str": "YYYY-MM-DD",
  "parsed_year": 2000,
  "status": "ready|pending|failed",
  "pose": {
    "yaw": 0.0,
    "pitch": 0.0,
    "roll": 0.0,
    "pose_source": "scrfd|3ddfa",
    "bucket": "frontal"
  },
  "metrics": {
    "nose_projection_ratio": 0.5,
    "orbit_depth_L_ratio": 0.3,
    ...
  },
  "texture_forensics": {
    "texture_silicone_prob": 0.1,
    "reliability_weight": 0.9,
    ...
  },
  "quality": {
    "overall_score": 0.8,
    "flags": {...}
  },
  "anomaly_flags": [...],
  "artifacts": {
    "uv_texture": "/storage/main/{id}/uv_texture.png",
    ...
  },
  "extracted_at": "ISO timestamp"
}
```

## Кэширование

### Уровни кэширования

1. **Service-level кэш** (core/service.py):
   - _records_cache: кэш записей по датасету с TTL 30 секунд
   - _main_records_cache: кэш main records
   - _calib_summary_cache: кэш сводки калибровки
   - Инвалидация при write_json или по TTL

2. **Reconstruction кэш** (pipeline/reconstruction.py):
   - _cache: dict[str, ReconstructionResult] с лимитом _max_cache_size (10)
   - Ключ: MD5(image_path) + device + backbone + neutral_expression
   - Автоматическая эвикция при достижении лимита с очисткой VRAM
   - MD5-хэш защищает от ложной инвалидации при копировании папок

3. **Pose detector кэш** (pipeline/detect_pose.py):
   - Ленивая инициализация 3DDFA модели (только при необходимости)
   - Singleton для тяжелых моделей

### Защита от OOM

Функция **_evict_cache_if_needed()** в reconstruction.py:
- Удаляет старые записи из кэша FIFO
- Явно удаляет тензоры (del)
- Принудительный gc.collect()
- Очистка VRAM (torch.cuda.empty_cache() или torch.mps.empty_cache())

## Cascade Engine - Многоступенчатая обработка

### cascade.py - CascadeEngine

Класс **CascadeEngine** реализует последовательную форензическую проверку пар фотографий:

Стадии каскада:
1. **Gate 0: Temporal Consistency** - проверка временной невозможности (impossible_short)
2. **Stage 1: Texture & Quality Fast Check** - быстрая проверка текстуры и качества (детекция силикона)
3. **Stage 2: Deep Geometry Analysis** - глубокий геометрический анализ (3D SNR)
4. **Synthesis: Bayesian Multi-Hypothesis Verdict** - синтез через байесовский движок

Функция **analyze_pair()**:
- Принимает photo_a, photo_b, date_a, date_b, timeline_context
- Возвращает ForensicVerdict с вероятностями H0/H1/H2
- При rejection quality gate возвращает UNCERTAIN с INSUFFICIENT_DATA

Компоненты:
- QualityGate: оценка качества изображений
- SkinTextureAnalyzer: текстурный анализ
- CalibrationAnalyzer: калибровочный анализ
- ChronologyAnalyzer: хронологический анализ
- BayesianMultiHypothesisEngine: байесовский движок
- PairComparisonEngine: движок парного сравнения
- ReconstructionAdapter: адаптер 3D реконструкции

## Pair Comparison Engine

### compare.py (pipeline) - PairComparisonEngine

Класс **PairComparisonEngine** оркестрирует полный поток сравнения двух реконструкций:

Функции:
- **_compute_linear_snr()**: Вычисление линейного SNR (без децибел) с защитой от взрывного роста
- **_extract_calibrated_geometry_evidence()**: Единое извлечение калиброванных геометрических доказательств
- **shared_vertex_indices()**: Пересечение видимых вершин двух моделей
- **_estimate_face_scale()**: Оценка масштаба лица из размаха точек (percentiles 25-75)

Методы:
- **compare_pair()**: Основное сравнение пары с выравниванием, скорингом и вердиктом
- **align_and_score()**: Выравнивание и вычисление метрик сходства
- **extract_macro_bone_metrics()**: Извлечение макро-костных метрик

Калибровка:
- CalibrationProtocol: протокол калибровки с decompose(signal, noise, snr)
- CalibrationDecomposition: разложение ошибки на сигнал и шум
- find_calibration_match(): поиск калибровочного фото по pose distance

IPD (Interpupillary Distance):
- Валиден только если оба глаза видны (|yaw| < 30°)
- _IPD_MAX_YAW_DEG = 30.0

## Persona Management

### persona.py - Кластеризация персон

Функция **cluster_personas()**:
- Группирует фотографии с похожим профилем геометрических аномалий
- Выявляет использование одного реквизита (маски) в разные годы
- Работает внутри каждого bucket (ракурса) отдельно

Алгоритм:
1. Группировка records по bucket
2. Векторизация метрик из BUCKET_METRIC_KEYS
3. TEXTURE_WEIGHT = 0.35 для текстурных метрик
4. TEXTURE_KEYS_INCLUDE: texture_silicone_prob, texture_pore_density, texture_specular_gloss, texture_lbp_complexity
5. Нормализация векторов по колонкам (min-max)
6. Кластеризация по евклидовому расстоянию (порог 0.2)
7. Возврат кластеров с persona_id, bucket, count, photo_ids, avg_profile

Результат:
- persona_id: уникальный ID кластера
- bucket: ракурс кластеризации
- count: количество фото в кластере
- photo_ids: список ID фото
- avg_profile: усредненный профиль метрик

## Recommendations System

### recommendations.py - Рекомендации по калибровке

Функция **build_recommendations()**:

Анализирует main_records и calibration_summary, генерирует рекомендации:

Типы рекомендаций:
1. **coverage_main**: покрытие основного датасета по ракурсам
   - priority: high если count == 0, medium если count < 3
   - description: нет покрытия или мало фото
   - benefit: непрерывная линия сравнения, меньше ложных переходов

2. **coverage_calibration**: покрытие калибровки
   - priority: medium если cal_count < 2
   - description: слабая калибровка
   - benefit: диапазоны шума, надежные допуски

3. **temporal_gap**: временные разрывы
   - priority: high если daysBetween > 30
   - description: разрыв между датами
   - benefit: фото вокруг midpoint сузит окно неопределенности

4. **anomaly_followup**: следствие за аномалиями
   - priority: critical для impossible_short (identity swap), high для transition
   - description: forensic_score, сочетание отклонений
   - benefit: подтверждение подмены или выявление ошибки экстракции

5. **metric_replace**: метрики со статусом replace
   - priority: medium
   - description: метрика нестабильна
   - benefit: замена калибровочных данных

## Longitudinal Analysis

### longitudinal.py - Longitudinal Model

Класс **LongitudinalModel** для продольного анализа изменений лица:

Функции:
- **fit_ageing_curve()**: Подгонка кривой старения по метрикам
- **predict_expected_values()**: Предсказание ожидаемых значений для года
- **compute_deviation()**: Вычисление отклонения от ожидаемой кривой
- **detect_ageing_anomalies()**: Детекция аномалий старения

Модель учитывает:
- Естественное старение (gradual changes)
- Временные факторы (вес, здоровье)
- Ракурс-специфичные паттерны

## Diary and Investigations

### diary.py - Дневник расследований

Функции:
- **get_diary()**: Получение всех записей дневника
- **add_diary_entry()**: Добавление новой записи
- **update_diary_entry()**: Обновление существующей записи

Структура записи:
- entry_id: уникальный ID
- timestamp: время создания
- title: заголовок
- content: содержание
- tags: теги
- related_photo_ids: связанные фотографии

### Investigations

Функции в service.py:
- **get_investigations()**: Список расследований
- **upsert_investigation()**: Создание/обновление расследования
- **delete_investigation()**: Удаление расследования

Структура расследования:
- inv_id: уникальный ID
- title: заголовок
- description: описание
- photo_ids: связанные фотографии
- status: статус (open, closed, pending)
- created_at, updated_at: временные метки

## Performance Optimization

### Оптимизации в pipeline/

1. **Кэширование реконструкции**:
   - MD5-хэш для ключа кэша
   - Лимит 10 записей с автоматической эвикцией
   - Очистка VRAM при эвикции

2. **Trimmed mean**:
   - TRIMMED_KEEP_RATIO = 0.8 для защиты от выбросов
   - MIN_KEEP_N = минимум значений для сохранения

3. **Матричные операции**:
   - Вычисление только верхнего треугольника матрицы N×N
   - Симметричное заполнение для H0

4. **Ленивая инициализация**:
   - 3DDFA модель инициализируется только при необходимости
   - Singleton для тяжелых моделей

### Оптимизации в core/

1. **Service-level кэш**:
   - TTL 30 секунд для записей
   - Инвалидация при write_json
   - Отдельные кэши для main, calibration, summary

2. **Робастная статистика**:
   - Median вместо mean
   - MAD (Median Absolute Deviation) вместо std
   - Trimmed mean для защиты от выбросов

3. **Batch processing**:
   - process_dataset() с progress_callback
   - limit и only_ids для частичной обработки

## Error Handling and Resilience

### Механизмы отказоустойчивости

1. **Quality Gate**:
   - Soft rejection вместо crash
   - INSUFFICIENT_DATA_UNREADABLE при ошибке чтения
   - FACE_TOO_SMALL при недостаточном разрешении

2. **Fallback механизмы**:
   - Pose detection: SCRFD → 3DDFA
   - Calibration: calibrated → fallback
   - Geometry evidence: calibrated → fallback → unavailable

3. **Защита от NaN/Inf**:
   - max(abs(noise), 0.005) в SNR
   - clamp() для ограничения значений
   - Проверка на finite в visibility

4. **Thread-safe операции**:
   - JobManager с threading.Lock()
   - Атомарные обновления статусов

5. **Логирование ошибок**:
   - try/except с logger.error()
   - Сохранение ошибок в JobRecord.errors
   - Продолжение работы при ошибках отдельных фото

## Testing and Validation

### Контроль качества данных

1. **Quality Gate**:
   - Laplacian variance > 100 для приемлемой резкости
   - Noise level < 25 для приемлемого шума
   - Face height > 150px для форензики текстуры

2. **Calibration health**:
   - stable: robust CV ≤ 0.12
   - marginal: robust CV ≤ 0.24
   - replace: robust CV > 0.24

3. **Хронологическая валидация**:
   - Проверка временной невозможности
   - Детекция скачков метрик
   - Флаги: impossible_short, transition, return_to_baseline

### Валидация результатов

1. **Байесовская валидация**:
   - Апостериорные вероятности H0/H1/H2
   - Confidence score
   - Fuzzy label для интерпретации

2. **SNR валидация**:
   - SNR_SIGNAL_THRESHOLD = 3.0 для сильного сигнала
   - SNR_UNCERTAIN_THRESHOLD = 1.5 для неопределенности

3. **Cross-validation**:
   - Сравнение внутри одного ракурса
   - Проверка консистентности во времени
   - Кластеризация персон для выявления повторов

## I/O и Форматы Данных

### io.py - I/O операции

Модуль для сериализации форензических данных:

Функция **build_forensic_payload()**:
- Генерирует стандартизированный JSON для хранения результатов
- Включает metadata (artifact_version, generated_at_utc, image paths, status, runtime_config)
- Summary: status, provisional_band, robust_provisional_band, geometry_error, similarity_score
- Alignment: method (rigid_umeyama_no_scale), residual_after
- Zones: список зон с id, name, error, score, delta_mm, shift_direction
- Diagnostics: диагностическая информация
- attach_confidence_level(): прикрепляет уровень уверенности

Функция **save_forensic_result()**:
- Сохраняет payload в JSON с indent=2, ensure_ascii=False
- Создает родительские директории при необходимости

Константа **ARTIFACT_VERSION**: версия формата артефактов

### batch_processor.py - Пакетная обработка

Класс **ForensicBatchProcessor** для анализа директорий:

Функция **process_directory()**:
- Обрабатывает все изображения в директории (jpg, jpeg, png)
- Проверяет EXCLUDED_FROM_ANALYSIS с логированием WARNING уровня
- Запускает cascade.analyze_single() для каждого фото
- Сохраняет индивидуальный passport для каждого фото
- Строит forensic_bundle.json с резюме
- Вызывает cleanup_artifacts() для очистки временных файлов

Структура bundle:
- version, generated_at, input_directory, photo_count
- passports: список результатов анализа

## Специализированные Метрики

### metrics.py - Метрики симметрии

Функция **compute_procrustes_symmetry()**:
- Вычисляет симметрию текстуры с Прокрустовым выравниванием 2D
- Параметры: uv_texture (512x512x3), lm_left, lm_right, conf_mask
- Алгоритм:
  1. Оценивает аффинную матрицу (Translation + Rotation + Scale) через SimilarityTransform
  2. Искажает текстуру по найденной трансформации (кубическая интерполяция, order=3)
  3. Зеркально отражает выровненную текстуру (np.fliplr)
  4. Вычисляет разницу в зонах с высоким доверием (conf_mask > 0.65)
  5. L1 норма (Absolute Difference) для устойчивости к бликам
- Возвращает symmetry_score (1.0 = идеал, 0.0 = полная асимметрия)

Функция **compute_symmetry_distance_map()**:
- Вычисляет карту расстояний внутри маски лица
- Исправляет баг инверсии маски (TX-05)
- Гарантирует бинарную маску (1 = лицо, 0 = фон)
- Использует scipy.ndimage.distance_transform_edt()
- Возвращает dist_map: 0 на фоне, растет к центру лица

## Diary System

### diary.py - Дневник расследований

Константа **DIARY_FILE**: storage/diary_db.json

Функция **add_diary_entry()**:
- Создает директорию при необходимости
- Добавляет запись с timestamp, author, content
- Сохраняет в JSON с indent=2, ensure_ascii=False
- Возвращает новую запись

Функция **get_diary_entries()**:
- Возвращает последние N записей (limit=10 по умолчанию)
- Обрабатывает JSONDecodeError при повреждении файла
- Возвращает пустой список если файл не существует

## Контракты Данных

### contract.py - Контракты для валидации

Модуль определяет контракты для валидации данных:

Функция **attach_confidence_level()**:
- Прикрепляет уровень уверенности на основе вероятностей
- Классифицирует: high, medium, low, unknown

Контракты обеспечивают:
- Валидацию входных данных
- Стандартизацию выходных форматов
- Совместимость между компонентами системы

## External Dependencies

### Внешние библиотеки и модели

**3DDFA_v3** (core/3ddfa_v3/):
- Нейросеть для 3D реконструкции лица
- Модели: face_model, face_box (RetinaFace детектор)
- Backbone: resnet50 (по умолчанию)
- Устройства: CPU, CUDA, MPS (Mac)
- Активы: face_model.npy

**head-pose-estimation** (/Users/victorkhudyakov/dutin/core/head-pose-estimation):
- SCRFD детектор для pose detection
- Модели: SCRFD, get_model
- Функции: compute_euler_angles_from_rotation_matrices
- Пороги поз: настраиваются через pose_settings.json

**uv_module/hd_uv_generator.py** (опционально):
- HDUVConfig, HDUVTextureGenerator
- Генерация HD UV текстур
- Интеграция через _UV_AVAILABLE флаг

**Библиотеки обработки изображений**:
- OpenCV (cv2): чтение/запись, Laplacian, medianBlur
- NumPy: векторные операции, SVD, percentiles
- PIL/Pillow: работа с изображениями
- PyTorch: GPU вычисления, тензоры
- scikit-image: LBP, GLCM, Gabor, canny, transform
- scikit-ndimage: distance_transform_edt
- Pydantic: валидация данных
- FastAPI: веб-сервер
- Uvicorn: ASGI сервер

## Конфигурация Runtime

### Runtime Config Snapshot

Функция **runtime_config_snapshot()** в utils.py:
- Создает снимок текущей конфигурации
- Включает версии библиотек, устройства, пороги
- Используется для воспроизводимости результатов

Параметры runtime:
- device: CPU/CUDA/MPS
- detector_device: устройство для детекции
- backbone: resnet50
- blur_threshold, noise_threshold
- TRIMMED_KEEP_RATIO, MIN_KEEP_N
- Z_TOLERANCE_RATIO
- PRIOR_SAME_PERSON, PRIOR_IDENTITY_SWAP

## Логирование

### Настройка логирования

main.py:
- LOG_DIR = logs/ в корне проекта
- Формат: timestamp [levelname] name: message
- Хендлеры:
  - FileHandler: logs/backend.log (encoding=utf-8)
  - StreamHandler: консоль
- Логгеры:
  - deeputin: основной логгер
  - forensic.pipeline: пайплайн
  - forensic.batch: пакетная обработка

Уровни логирования:
- DEBUG: детальная отладка
- INFO: информационные сообщения
- WARNING: предупреждения (exclusion, fallback)
- ERROR: ошибки с продолжением работы
- CRITICAL: критические ошибки

## Безопасность и Аудит

### Аудитный трейл

**EXCLUDED_FROM_ANALYSIS**:
- Список photo_id для исключения из анализа
- Логирование на WARNING уровне с timestamp
- Причина: EXCLUDED_FROM_ANALYSIS

**Calibration overrides**:
- calibration_overrides.json: ручные переопределения
- Поля: photo_id, calibration_photo_id, reason, author
- API: POST /api/calibration/override

**Job errors**:
- JobRecord.errors: список ошибок задачи
- Сохраняется в JSON для аудита
- Включает traceback при критических ошибках

### Защита данных

**MD5 хэширование**:
- compute_image_hash(): защита кэша от ложной инвалидации
- Ключ кэша включает хэш содержимого файла
- Защищает от копирования папок с изменением mtime

**Валидация входных данных**:
- Pydantic модели для API endpoints
- Проверка типов и диапазонов
- Soft rejection вместо crash

**Изоляция датасетов**:
- main и calibration разделены
- temp изолирован для временных сравнений
- Отдельные директории storage/

## Метрики Производительности

### Ключевые метрики

1. **Время извлечения**:
   - Pose detection: ~100-500ms (CPU), ~50-100ms (GPU)
   - 3D reconstruction: ~500-2000ms (CPU), ~100-300ms (GPU)
   - Texture analysis: ~200-500ms
   - Full extraction: ~1-3s (CPU), ~0.3-1s (GPU)

2. **Время сравнения**:
   - Pair comparison: ~50-200ms (с кэшем reconstruction)
   - Matrix N×N: O(N²) операций, ~10ms для N=10

3. **Память**:
   - Reconstruction кэш: ~10-50MB на запись
   - Service кэш: ~1-10MB для записей
   - VRAM: ~2-4GB для 3DDFA на GPU

4. **Размер storage**:
   - summary.json: ~5-10KB на фото
   - reconstruction_v1.pkl: ~10-30MB на фото
   - uv_texture.png: ~500KB-2MB на фото
   - Итого: ~15-40MB на фото

### Оптимизация производительности

1. **Параллельная обработка**:
   - JobManager для фоновых задач
   - Batch processing для директорий
   - Progress callback для отслеживания прогресса

2. **Кэширование**:
   - Reconstruction кэш с эвикцией
   - Service кэш с TTL
   - MD5-хэш для ключей

3. **Ленивая загрузка**:
   - 3DDFA модель только при необходимости
   - On-demand extraction для temp фото
   - Lazy loading summaries

## Деплоймент и Инфраструктура

### Требования к окружению

**Python**: 3.9+
**GPU**: NVIDIA CUDA 11.0+ (опционально) или Apple MPS (M1/M2)
**RAM**: 8GB+ минимум, 16GB+ рекомендовано
**Диск**: 50GB+ для storage (зависит от количества фото)

**Зависимости**:
- torch, torchvision, torchaudio
- opencv-python, opencv-python-headless
- numpy, scipy, scikit-image
- fastapi, uvicorn, pydantic
- pillow
- matplotlib (для визуализации, опционально)

### Запуск в продакшене

**Docker (рекомендуется)**:
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8011"]
```

**Systemd service**:
```ini
[Unit]
Description=DEEPUTIN Backend
After=network.target

[Service]
Type=simple
User=deeputin
WorkingDirectory=/opt/deeputin
ExecStart=/opt/deeputin/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8011
Restart=always

[Install]
WantedBy=multi-user.target
```

**Nginx reverse proxy**:
```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8011;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    client_max_body_size 100M;
}
```

### Мониторинг

**Health check**: GET /api/health
**Логи**: logs/backend.log
**Метрики**: /api/overview, /api/cache/summary
**Jobs**: /api/jobs для статуса фоновых задач

### Backup и Recovery

**Storage backup**:
- Регулярное резервирование storage/
- Включает main/, calibration/, temp/, метафайлы
- Использовать rsync или rclone

**Configuration backup**:
- core/config.py
- pose_settings.json
- calibration_overrides.json

**Recovery**:
- POST /api/reset-all для полного сброса