# scripts/bibliografia.py - Referencias verificadas una a una (formato IEEE)
"""Bibliografía del informe final, comprobada contra la fuente original.

Cada entrada se verificó en arXiv, dblp, ACM DL, Springer, IEEE o el sitio del
editor. Las que no pudieron localizarse se retiraron y se sustituyeron por
trabajos reales sobre el mismo tema; el registro de esa depuración queda en
CORRECCIONES para que la sección de metodología pueda citarlo.

Los números son estables: el texto del informe cita [n] y `REFERENCIAS[n-1]`
devuelve la entrada. No renumerar sin actualizar las citas en el cuerpo.
"""

from __future__ import annotations

REFERENCIAS: tuple[str, ...] = (
    # 1
    'A. Vaswani et al., "Attention is all you need," en Advances in Neural '
    'Information Processing Systems 30 (NeurIPS), 2017, pp. 5998-6008.',
    # 2
    'J. Devlin, M.-W. Chang, K. Lee y K. Toutanova, "BERT: Pre-training of deep '
    'bidirectional transformers for language understanding," en Proc. NAACL-HLT, '
    '2019, pp. 4171-4186.',
    # 3
    'W.-C. Kang y J. McAuley, "Self-attentive sequential recommendation," en '
    'Proc. IEEE Int. Conf. Data Mining (ICDM), 2018, pp. 197-206.',
    # 4
    'F. Sun et al., "BERT4Rec: Sequential recommendation with bidirectional '
    'encoder representations from transformer," en Proc. ACM CIKM, 2019, '
    'pp. 1441-1450.',
    # 5
    'T. Bertin-Mahieux, D. P. W. Ellis, B. Whitman y P. Lamere, "The million song '
    'dataset," en Proc. 12th Int. Society for Music Information Retrieval Conf. '
    '(ISMIR), 2011, pp. 591-596.',
    # 6
    'M. Buffa et al., "The WASABI dataset: Cultural, lyrics and audio analysis '
    'metadata about 2 million popular commercially released songs," en The '
    'Semantic Web - ESWC 2021, Lecture Notes in Computer Science, vol. 12731. '
    'Cham: Springer, 2021, pp. 515-531, doi: 10.1007/978-3-030-77385-4_31.',
    # 7
    'L. Moura, E. Fontelles, V. Sampaio y M. França, "Music dataset: Lyrics and '
    'metadata from 1950 to 2019," Mendeley Data, V2, 2020, '
    'doi: 10.17632/3t9vbwxgr5.2.',
    # 8
    'K. Choi, S. Doh y J. Nam, "TalkPlayData 2: An agentic synthetic data pipeline '
    'for multimodal conversational music recommendation," arXiv:2509.09685, 2025.',
    # 9
    'P. Lewis et al., "Retrieval-augmented generation for knowledge-intensive NLP '
    'tasks," en Advances in Neural Information Processing Systems 33 (NeurIPS), '
    '2020, pp. 9459-9474.',
    # 10
    'Y. Gao et al., "Retrieval-augmented generation for large language models: '
    'A survey," arXiv:2312.10997, 2023.',
    # 11
    'M. Armbrust et al., "Delta Lake: High-performance ACID table storage over '
    'cloud object stores," Proc. VLDB Endow., vol. 13, n.º 12, pp. 3411-3424, 2020.',
    # 12
    'K. Järvelin y J. Kekäläinen, "Cumulated gain-based evaluation of IR '
    'techniques," ACM Trans. Inf. Syst., vol. 20, n.º 4, pp. 422-446, 2002.',
    # 13
    'C.-N. Ziegler, S. M. McNee, J. A. Konstan y G. Lausen, "Improving '
    'recommendation lists through topic diversification," en Proc. 14th Int. '
    'Conf. World Wide Web (WWW), 2005, pp. 22-32.',
    # 14
    'M. Kaminskas y D. Bridge, "Diversity, serendipity, novelty, and coverage: '
    'A survey and empirical analysis of beyond-accuracy objectives in recommender '
    'systems," ACM Trans. Interact. Intell. Syst., vol. 7, n.º 1, Art. n.º 5, '
    'pp. 1-42, 2017, doi: 10.1145/2926720.',
    # 15
    'L. Porcaro, C. Castillo y E. Gómez, "Diversity by design in music recommender '
    'systems," Trans. Int. Soc. Music Inf. Retr., vol. 4, n.º 1, pp. 114-126, '
    '2021, doi: 10.5334/tismir.106.',
    # 16
    'T. Baltrušaitis, C. Ahuja y L.-P. Morency, "Multimodal machine learning: '
    'A survey and taxonomy," IEEE Trans. Pattern Anal. Mach. Intell., vol. 41, '
    'n.º 2, pp. 423-443, 2019.',
    # 17
    'J. A. Russell, "A circumplex model of affect," J. Pers. Soc. Psychol., '
    'vol. 39, n.º 6, pp. 1161-1178, 1980.',
    # 18
    'I. Loshchilov y F. Hutter, "Decoupled weight decay regularization," en '
    'Proc. Int. Conf. Learning Representations (ICLR), 2019.',
    # 19
    'B. Jacob et al., "Quantization and training of neural networks for efficient '
    'integer-arithmetic-only inference," en Proc. IEEE/CVF CVPR, 2018, '
    'pp. 2704-2713, doi: 10.1109/CVPR.2018.00286.',
    # 20
    'A. Paszke et al., "PyTorch: An imperative style, high-performance deep '
    'learning library," en Advances in Neural Information Processing Systems 32 '
    '(NeurIPS), 2019, pp. 8024-8035.',
    # 21
    'T. Wolf et al., "Transformers: State-of-the-art natural language processing," '
    'en Proc. EMNLP: System Demonstrations, 2020, pp. 38-45.',
    # 22
    'P. Mattson et al., "MLPerf: An industry standard benchmark suite for machine '
    'learning performance," IEEE Micro, vol. 40, n.º 2, pp. 8-16, 2020, '
    'doi: 10.1109/MM.2020.2974843.',
    # 23
    'C. C. Aggarwal, Recommender Systems: The Textbook. Cham: Springer, 2016.',
    # 24
    'G. Adomavicius y A. Tuzhilin, "Toward the next generation of recommender '
    'systems: A survey of the state-of-the-art and possible extensions," IEEE '
    'Trans. Knowl. Data Eng., vol. 17, n.º 6, pp. 734-749, 2005.',
    # 25
    'C. A. Gómez-Uribe y N. Hunt, "The Netflix recommender system: Algorithms, '
    'business value, and innovation," ACM Trans. Manage. Inf. Syst., vol. 6, '
    'n.º 4, Art. n.º 13, pp. 1-19, 2015, doi: 10.1145/2843948.',
    # 26
    'IFPI, "Global music report 2025: State of the industry," Londres, 2025. '
    '[En línea]. Disponible en: '
    'https://www.ifpi.org/wp-content/uploads/2024/03/GMR2025_SOTI.pdf',
    # 27
    'S. Doh, K. Choi y J. Nam, "TALKPLAY: Multimodal music recommendation with '
    'large language models," arXiv:2502.13713, 2025.',
    # 28
    'Z. Dong, B. Chen, X. Liu, P. Polak y P. Zhang, "MuseChat: A conversational '
    'music recommendation system for videos," en Proc. IEEE/CVF CVPR, 2024 '
    '(arXiv:2310.06282).',
    # 29
    'X. Huang, J. Lian, Y. Lei, J. Yao, D. Lian y X. Xie, "Recommender AI agent: '
    'Integrating large language models for interactive recommendations," '
    'arXiv:2308.16505, 2023.',
    # 30
    'A. Zhang, Y. Chen, L. Sheng, X. Wang y T.-S. Chua, "On generative agents in '
    'recommendation," en Proc. 47th Int. ACM SIGIR Conf. Research and Development '
    'in Information Retrieval, 2024 (arXiv:2310.10108).',
    # 31
    'J. Zhang et al., "AgentCF: Collaborative learning with autonomous language '
    'agents for recommender systems," en Proc. ACM Web Conf. (WWW), 2024 '
    '(arXiv:2310.09233).',
    # 32
    'L. Porcaro, E. Gómez y C. Castillo, "Assessing the impact of music '
    'recommendation diversity on listeners: A longitudinal study," ACM Trans. '
    'Recomm. Syst., vol. 2, n.º 1, Art. n.º 3, pp. 1-47, 2024, '
    'doi: 10.1145/3608487.',
    # 33
    'S. Doh, K. Choi y J. Nam, "TalkPlay-Tools: Conversational music recommendation '
    'with LLM tool calling," arXiv:2510.01698, 2025.',
    # 34
    'Ò. Celma, Music Recommendation and Discovery: The Long Tail, Long Fail, and '
    'Long Play in the Digital Music Space. Berlín: Springer, 2010.',
    # 35
    'M. Schedl, H. Zamani, C.-W. Chen, Y. Deldjoo y M. Elahi, "Current challenges '
    'and visions in music recommender systems research," Int. J. Multimed. Inf. '
    'Retr., vol. 7, n.º 2, pp. 95-116, 2018, doi: 10.1007/s13735-018-0154-2.',
    # 36
    'P. Chapman, J. Clinton, R. Kerber, T. Khabaza, T. Reinartz, C. Shearer y '
    'R. Wirth, CRISP-DM 1.0: Step-by-step data mining guide, SPSS Inc., 2000.',
)

# Depuración de la bibliografía del anteproyecto. Cada fila documenta qué se
# citaba, qué se encontró al verificar y con qué se reemplazó. Sirve de evidencia
# para la observación del evaluador sobre confiabilidad y actualidad de fuentes.
CORRECCIONES: tuple[tuple[str, str, str], ...] = (
    ('WASABI atribuido a Sordo, Celma y Serra en ISMIR',
     'Autoría y evento incorrectos: el artículo es de Buffa et al., ESWC 2021, '
     'LNCS 12731, pp. 515-531.',
     'Referencia [6] corregida con DOI verificado.'),
    ('Porcaro, Vincent y Moussallam, ISMIR 2021, pp. 716-723',
     'El título y las páginas no existen. El trabajo real de Porcaro sobre '
     'diversidad es Porcaro, Castillo y Gómez, TISMIR 4(1), 2021.',
     'Referencia [15]; se añade [32] (estudio longitudinal, TORS 2024).'),
    ('Vaswani et al., "Transformers: Foundations and applications", Commun. ACM 2023',
     'No existe tal artículo en Communications of the ACM.',
     'Se cita el artículo original [1].'),
    ('arXiv:2402.01876 como sesgo de popularidad multimodal',
     'El identificador corresponde a clasificación de jets en FPGA para el HL-LHC '
     '(física de partículas), no a recomendación musical.',
     'Se retira; el sesgo de popularidad se sustenta en [13], [14], [34] y [35].'),
    ('arXiv:2404.11235 como "PISA" musical',
     'El identificador corresponde a un proceso autorregresivo bayesiano con '
     'cambio de régimen (econometría).',
     'Se retira; recomendación conversacional multimodal se sustenta en [27] y [28].'),
    ('arXiv:2405.06321 como MuseChat',
     'El identificador corresponde a dimensión de correlación del lenguaje natural. '
     'MuseChat es arXiv:2310.06282, CVPR 2024, Dong et al.',
     'Referencia [28] corregida.'),
    ('Medina, Rev. Comun. Digit. 14(2), 2022',
     'Artículo y revista no localizables en ninguna base académica.',
     'Se retira; se usa [35] (Schedl et al., IJMIR 2018).'),
    ('Celma, J. New Music Res. 52(2), 2023',
     'No existe ese artículo; la obra de Celma sobre larga cola es el libro de '
     'Springer de 2010.',
     'Referencia [34] corregida.'),
    ('Naveeda, "Large language models", AI Rev. J. 2024',
     'Revista y artículo no localizables.',
     'Se retira; fundamentos de LLM y agentes se sustentan en [21], [29], [30], [31].'),
    ('TalkPlay, "Technical White Paper", 2024',
     'No existe tal white paper. TalkPlay es un artículo de Doh, Choi y Nam.',
     'Referencias [27] y [8]; se añade [33] (TalkPlay-Tools, 2025).'),
    ('Huang et al. como autores de TalkPlay',
     'Autoría incorrecta (confusión con InteRecAgent, de Huang et al.).',
     '[27] Doh, Choi y Nam; [29] Huang et al. para InteRecAgent.'),
    ('Gómez-Uribe y Hunt, ACM TMIS, dic. 2016',
     'Fecha incorrecta: publicado el 28 de diciembre de 2015.',
     'Referencia [25] con año y DOI corregidos.'),
    ('Kaminskas y Bridge, ACM TiiS, 2016',
     'El número corresponde a marzo de 2017 (vol. 7, n.º 1, Art. 5).',
     'Referencia [14] con año, artículo y DOI corregidos.'),
    ('Jacob et al., título abreviado de cuantización',
     'El título completo es "…for efficient integer-arithmetic-only inference".',
     'Referencia [19] con título completo y DOI.'),
    ('IFPI: "el streaming creció 9,5 %"',
     'El 9,5 % corresponde solo al streaming por suscripción de pago; el streaming '
     'con publicidad creció 1,2 %. Los ingresos totales de 2024 fueron '
     'US$ 29,6 mil millones (+4,8 %).',
     'Referencia [26]; la cifra se precisa en el planteamiento del problema.'),
)


def citar(numeros: list[int] | tuple[int, ...]) -> str:
    """'[1], [3]' a partir de números de referencia."""
    return ", ".join(f"[{n}]" for n in numeros)