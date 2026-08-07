#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build gs_supplementary_results.json: raw GS data + dedup against existing."""
import json, re, os

HERE = os.path.dirname(os.path.abspath(__file__))

RAW = [
# ── Cluster A: medical LLM benchmark ──
("A_medical_llm_benchmark","Assessment of large language models in clinical reasoning: a novel benchmarking study","LG McCoy, R Swamy, N Sagar, M Wang, S Bacchi","NEJM AI","2025","81","https://ai.nejm.org/doi/abs/10.1056/AIdbp2500120"),
("A_medical_llm_benchmark","Medical large language model benchmarks should prioritize construct validity","A Alaa, T Hartvigsen, N Golchini, S Dutta","arXiv:2503.10694","2025","32","https://arxiv.org/abs/2503.10694"),
("A_medical_llm_benchmark","Performance of large language models on medical oncology examination questions","JB Longwell, I Hirsch, F Binder","JAMA Network Open","2024","106","https://jamanetwork.com/journals/jamanetworkopen/article-abstract/2820094"),
("A_medical_llm_benchmark","Assessing and optimizing large language models on spondyloarthritis multi-choice question answering","A Wang, Y Wu, X Ji, X Wang, J Hu","JMIR Research Protocols","2024","11","https://www.researchprotocols.org/2024/1/e57001"),
("A_medical_llm_benchmark","MedGUIDE: benchmarking clinical decision-making in large language models","X Li, M Gao, Y Hao, T Li, G Wan, Z Wang","arXiv:2505.11613","2025","14","https://arxiv.org/abs/2505.11613"),
("A_medical_llm_benchmark","EHRNoteQA: an LLM benchmark for real-world clinical practice using discharge summaries","S Kweon, J Kim, H Kwak, D Cha","NeurIPS 2024","2024","58","https://proceedings.neurips.cc/paper_files/paper/2024/hash/e15c4afff22f12c4986c1fcb4e941e03-Abstract-Datasets_and_Benchmarks_Track.html"),
("A_medical_llm_benchmark","Beyond multiple-choice questions: rethinking evaluation frameworks for LLMs for clinical medicine","Z Jiang, H Chen, Y Wu, Y Qin, C Pei, D Zeng","Intelligent Medicine","2026","5","https://mednexus.org/doi/abs/10.1016/j.imed.2026.01.001"),
("A_medical_llm_benchmark","Comparative evaluation of LLMs in clinical oncology","NR Rydzewski, D Dinakaran, SG Zhao, E Ruppin","NEJM AI","2024","133","https://ai.nejm.org/doi/abs/10.1056/AIoa2300151"),
("A_medical_llm_benchmark","Benchmarking LLMs on authentic cases from medical journals","W Liu, J Chen, Y Yang, P Tiwari, W Chen","Findings of ACL 2026","2026","0","https://aclanthology.org/2026.findings-acl.767/"),
("A_medical_llm_benchmark","MedQA-CS: benchmarking large language models clinical skills using an AI-SCE framework","Z Yao, Z Zhang, C Tang, X Bian, Y Zhao","arXiv","2024","42","https://arxiv.org/abs/2407.04300"),
("A_medical_llm_benchmark","MediQ: question-asking LLMs and a benchmark for reliable interactive clinical reasoning","SS Li, V Balachandran, S Feng","NeurIPS 2024","2024","214","https://proceedings.neurips.cc/paper_files/paper/2024/hash/32b80425554e081204e5988ab1c9719a-Abstract-Conference.html"),
("A_medical_llm_benchmark","MedQA-CS: OSCE-style benchmark for evaluating LLM clinical skills","Z Yao, Z Zhang, C Tang, X Bian, Y Zhao","EACL 2026","2026","6","https://aclanthology.org/2026.eacl-long.292/"),
("A_medical_llm_benchmark","LLMEval-Med: a real-world clinical benchmark for medical LLMs with physician validation","M Zhang, Y Shen, Z Li, H Sha, B Hu","Findings of EMNLP 2025","2025","21","https://arxiv.org/abs/2506.04078"),
("A_medical_llm_benchmark","Medical reasoning with large language models: a systematic review and evaluation","X Ren, C Fan, W Ma, H He, C Gao, X Zhao","Wiley","2026","1","https://onlinelibrary.wiley.com/doi/abs/10.1002/inm3.70056"),
("A_medical_llm_benchmark","Clinician-level agreement without clinical caution: LLM evaluator limits in medical AI benchmarking","W Philipp, F Fassbender, T Langer, M Pauly","arXiv:2607.01103","2026","1","https://arxiv.org/abs/2607.01103"),
("A_medical_llm_benchmark","Benchmarking clinical reasoning in large language models: a comparative assessment study","T Prade, M Samwald","medRxiv","2026","0","https://www.medrxiv.org/content/10.64898/2026.03.13.26347597.abstract"),
("A_medical_llm_benchmark","MedDialogRubrics: benchmark and evaluation framework for multi-turn medical consultations","L Gong, W Fang, T Yang, D Tao, C Guo, P Wei","arXiv:2601.03023","2026","14","https://arxiv.org/abs/2601.03023"),
("A_medical_llm_benchmark","A benchmark for long-form medical question answering","P Hosseini, JM Sin, B Ren, BG Thomas, E Nouri","arXiv:2411.09834","2024","32","https://arxiv.org/abs/2411.09834"),
("A_medical_llm_benchmark","Large language models in the clinic: a comprehensive benchmark","F Liu, Z Li, H Zhou, Q Yin, J Yang, X Tang","arXiv:2405.00716","2024","49","https://arxiv.org/abs/2405.00716"),
("A_medical_llm_benchmark","Assessing large language models for medical QA: zero-shot and LLM-as-a-judge evaluation","SES Adib, AA Sani, EA Esham, A Abrar","IEEE","2025","2","https://ieeexplore.ieee.org/abstract/document/11491589/"),
# ── Cluster B: EHR/RWD benchmark ──
("B_ehr_rwd_benchmark","Assessment of the integrity of real-time electronic health record data used in clinical research","J Liu, S Pandya, A Coppi, HP Young, HM Krumholz","PLOS ONE","2026","3","https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0340287"),
("B_ehr_rwd_benchmark","EHRNoteQA: a patient-specific QA benchmark for evaluating LLMs in clinical settings","S Kweon, J Kim, H Kwak, D Cha, H Yoon","PhysioNet","2024","12","https://physionet.org/content/ehr-notes-qa-llms/1.0.0/"),
("B_ehr_rwd_benchmark","Generating clinically realistic EHR data via a hierarchy-and-semantics-guided transformer","G Zhou, S Barbieri","arXiv:2502.20719","2025","6","https://arxiv.org/abs/2502.20719"),
("B_ehr_rwd_benchmark","EHR-Complex: benchmarking medical agents for complex clinical reasoning","Y Qiao, L Liu, Y Shen, J Wang, J Gu, Z Chu","arXiv:2606.23301","2026","1","https://arxiv.org/abs/2606.23301"),
("B_ehr_rwd_benchmark","Benchmarking emergency department prediction models with ML and public EHR","F Xie, J Zhou, JW Lee, M Tan, S Li","Scientific Data","2022","109","https://www.nature.com/articles/s41597-022-01782-9"),
("B_ehr_rwd_benchmark","Framework for real-time anomaly detection in large-scale EHR databases using MIMIC-IV eICU-CRD","MX Zhang, D Osei-Bonsu","DATAMIND","2026","1","https://inatgi.in/index.php/dm/article/download/506/424"),
("B_ehr_rwd_benchmark","Generating synthetic EHR data: a methodological scoping review with benchmarking","X Chen, Z Wu, X Shi, H Cho","JAMIA","2025","27","https://academic.oup.com/jamia/article-abstract/32/7/1227/8155975"),
("B_ehr_rwd_benchmark","CliniQ: a multi-faceted benchmark for EHR retrieval with semantic match assessment","Z Zhao, H Yuan, J Liu, H Chen, H Ying, S Zhou","arXiv:2502.06252","2025","4","https://arxiv.org/abs/2502.06252"),
("B_ehr_rwd_benchmark","Real-world clinical datasets in practice: applications for learners and health services teams","JF Wood, JJ Tan, HM Eby, WM Rees","Clinical and Translational Science","2026","0","https://ascpt.onlinelibrary.wiley.com/doi/abs/10.1111/cts.70625"),
("B_ehr_rwd_benchmark","EHRSQL: a practical text-to-SQL benchmark for electronic health records","G Lee, H Hwang, S Bae, Y Kwon","NeurIPS 2022","2022","131","https://proceedings.neurips.cc/paper_files/paper/2022/hash/643e347250cf9289e5a2a6c1ed5ee42e-Abstract-Datasets_and_Benchmarks.html"),
("B_ehr_rwd_benchmark","An EHR data standardisation pipeline using the MIMIC-III dataset","J Gregorio, A Lemanska, B Cieszynski, N Peric","BIOSTEC 2026","2026","1",""),
("B_ehr_rwd_benchmark","Leveraging MIMIC datasets for better digital health: a review on open problems and progress","A Khaled, M Sabir, R Qureshi, CM Caruso","arXiv:2506.12808","2025","10","https://arxiv.org/abs/2506.12808"),
("B_ehr_rwd_benchmark","A multi-world synthetic benchmark for evaluating RSCE in clinical machine learning","N Piyavechvirat, YJ Huang, QMU Haq","IEEE Access","2026","0","https://ieeexplore.ieee.org/abstract/document/11404134/"),
("B_ehr_rwd_benchmark","A multifaceted benchmarking of synthetic EHR generation models","C Yan, Y Yan, Z Wan, Z Zhang, L Omberg","Nature Communications","2022","178","https://www.nature.com/articles/s41467-022-35295-1"),
("B_ehr_rwd_benchmark","Replication of real-world evidence in oncology using EHR data extracted by ML","CM Benedum, A Sondhi, E Fidyk, AB Cohen","Cancers","2023","38","https://www.mdpi.com/2072-6694/15/6/1853"),
("B_ehr_rwd_benchmark","Developing real-world evidence from real-world data: transforming raw data into analytical datasets","L Bastarache, JS Brown, JJ Cimino","Learning Health Systems","2022","68","https://onlinelibrary.wiley.com/doi/abs/10.1002/lrh2.10293"),
("B_ehr_rwd_benchmark","Real-world data for clinical evidence generation in oncology","S Khozin, GM Blumenthal","JNCI","2017","394","https://academic.oup.com/jnci/article-abstract/109/11/djx187/4157738"),
("B_ehr_rwd_benchmark","From real-world EHR data to real-world results using AI","R Knevel, KP Liao","Annals of the Rheumatic Diseases","2023","194","https://ard.bmj.com/content/82/3/306.abstract"),
("B_ehr_rwd_benchmark","Assessing function of electronic health records for real-world data generation","D Guinn, EE Wilhelm, G Lieberman","BMJ Evidence-Based Medicine","2019","13","https://ebm.bmj.com/content/24/3/95.abstract"),
# ── Cluster C: lab test order prediction ──
("C_lab_test_order_prediction","Targeting repetitive laboratory testing with EHR-embedded predictive decision support","N Rabbani, SP Ma, RC Li, M Winget, S Weber","Clinical Chemistry","2023","28","https://www.sciencedirect.com/science/article/pii/S0009912023000024"),
("C_lab_test_order_prediction","Clinical decision support for laboratory testing","AEO Hughes, R Jackups Jr","Clinical Chemistry","2022","29","https://academic.oup.com/clinchem/article-abstract/68/3/402/6453839"),
("C_lab_test_order_prediction","OrderRex: clinical order decision support and outcome predictions by data-mining EMR","JH Chen, T Podchiyska","JAMIA","2016","74","https://academic.oup.com/jamia/article-abstract/23/2/339/2572407"),
("C_lab_test_order_prediction","Predicting laboratory test ordering in emergency departments using integrated EHR ML","X Zhang, H Ling, X Zhang, A Zhang","JMIR Medical Informatics","2026","0","https://medinform.jmir.org/2026/1/e85255"),
("C_lab_test_order_prediction","Developing and maintaining clinical decision support using clinical knowledge and ML: order sets","Y Zhang, R Trepp, W Wang, J Luna","JAMIA","2018","14","https://academic.oup.com/jamia/article-abstract/25/11/1547/5067938"),
("C_lab_test_order_prediction","Use of ML to predict CDS compliance reduce alert burden and evaluate duplicate lab test alerts","JM Baron, R Huang, D McEvoy, AS Dighe","JAMIA Open","2021","36","https://academic.oup.com/jamiaopen/article-abstract/4/1/ooab006/6154712"),
("C_lab_test_order_prediction","Integrating pharmacogenomics into EHR with clinical decision support","JK Hicks, HM Dunnenberger","American Journal of Health-System Pharmacy","2016","180","https://academic.oup.com/ajhp/article-abstract/73/23/1967/5102166"),
("C_lab_test_order_prediction","Laboratory test-ordering patterns carry an early prognostic signal in EHR","S Baichoo, A Abedi, B Rubin, B Wang","Research Square","2026","0",""),
("C_lab_test_order_prediction","The effects of computerized CDS systems on laboratory test ordering: a systematic review","N Delvaux, K Van Thienen","American Journal of Clinical Pathology","2017","66","https://aplm.kglmeridian.com/view/journals/arpa/141/4/article-p585.xml"),
("C_lab_test_order_prediction","Integrating medication recommendation and lab test response prediction for enhanced CDS","S Bhoi, ML Lee, W Hsu, NC Tan","AAAI Symposium","2023","1","https://ojs.aaai.org/index.php/AAAI-SS/article/view/27489"),
("C_lab_test_order_prediction","Clinical decision support for hematology laboratory test utilization","R Jackups Jr, JJ Szymanski","International Journal of Laboratory Hematology","2017","23","https://onlinelibrary.wiley.com/doi/abs/10.1111/ijlh.12679"),
("C_lab_test_order_prediction","Impact of a CDS system in an EHR to enhance detection of alpha1-antitrypsin deficiency","A Jain, K McCarthy, M Xu, JK Stoller","Chest","2011","54","https://www.sciencedirect.com/science/article/pii/S0012369211603644"),
("C_lab_test_order_prediction","Laboratory test ordering in inpatient hospitals: systematic review on CDS effects","S Zare, Z Meidani, M Shirdeli, E Nabovati","BMC Medical Informatics and Decision Making","2021","27","https://link.springer.com/article/10.1186/s12911-020-01384-8"),
("C_lab_test_order_prediction","Pharmacogenomics implementation through end-to-end CDS: ten years from PREDICT","M Liu, CL Vnencak-Jones, BP Roland","Clinical Pharmacology and Therapeutics","2021","70","https://ascpt.onlinelibrary.wiley.com/doi/abs/10.1002/cpt.2079"),
("C_lab_test_order_prediction","OrderRex clinical user testing: randomized trial of recommender system decision support","A Kumar, RC Aikens, J Hom, L Shieh","JAMIA","2020","23","https://academic.oup.com/jamia/article-abstract/27/12/1850/5940667"),
("C_lab_test_order_prediction","Decision support tools within the electronic health record","JW Rudolf, AS Dighe","Clinics in Laboratory Medicine","2019","33","https://www.labmed.theclinics.com/article/S0272-2712(19)30001-0/abstract"),
("C_lab_test_order_prediction","Clinical decision support systems","ATM Wasylewicz","Fundamentals of Clinical Data Science","2018","266","https://library.oapen.org/bitstream/handle/20.500.12657/22918/1007243.pdf"),
("C_lab_test_order_prediction","Clinical decision support systems for improving diagnostic accuracy and precision medicine","C Castaneda, K Nalley, C Mannion","Journal of Clinical Bioinformatics","2015","593","https://link.springer.com/article/10.1186/s13336-015-0019-3"),
("C_lab_test_order_prediction","EHRs connect research and practice: predictive modeling AI and clinical decision support","CC Bennett, TW Doub, R Selove","Health Policy and Technology","2012","74","https://www.sciencedirect.com/science/article/pii/S221188371200038X"),
("C_lab_test_order_prediction","Optimizing CDS alerts in EMR: systematic review of reported strategies","BA Van Dort, WY Zheng, V Sundar","JAMIA","2021","88","https://academic.oup.com/jamia/article-abstract/28/1/177/5981524"),
# ── Cluster D: association rule clinical ──
("D_association_rule_clinical","Comorbidity patterns of older lung cancer patients: association rules analysis based on EMR","J Feng, X Mu, L Ma, W Wang","IJERPH","2020","27","https://www.mdpi.com/1660-4601/17/23/9119"),
("D_association_rule_clinical","Discovering sequential patterns and interrelations among multiple diseases in EMR using cSPADE","H Ma, Q Huang, H Zhang, H Song, B Zhang","International Journal of Public Health","2025","5","https://link.springer.com/article/10.1186/s13690-025-01589-1"),
("D_association_rule_clinical","Mining comorbidities of opioid use disorder from FDA AERS and patient EHR","Y Pan, R Xu","BMC Medical Informatics and Decision Making","2022","14","https://link.springer.com/article/10.1186/s12911-022-01869-8"),
("D_association_rule_clinical","Comorbidity combinations in schizophrenia inpatients using association rule mining","X Han, F Jiang, J Needleman, H Zhou, C Yao","Asian Journal of Psychiatry","2022","19","https://www.sciencedirect.com/science/article/pii/S187620182100383X"),
("D_association_rule_clinical","Identifying latent patterns of intimate partner violence using EHR and association rule mining","A Tabaie, SA Wyand, F Cao","AMIA Annual Symposium","2026","1","https://pmc.ncbi.nlm.nih.gov/articles/PMC12919600/"),
("D_association_rule_clinical","Real-time association rule mining for medical diagnosis and patient monitoring","P Selvakumar, S Chib, P Kalbande","IGI Global","2026","1","https://www.igi-global.com/chapter/real-time-association-rule-mining-for-medical-diagnosis-and-patient-monitoring/403763"),
("D_association_rule_clinical","Uncovering hidden patterns: association rule mining for disease detection and treatment planning","A Agrawal, MI Ali, M Shaikh, S Somesula","IGI Global","2026","0","https://www.igi-global.com/chapter/uncovering-hidden-patterns/403755"),
("D_association_rule_clinical","Using electronic patient records to discover disease correlations and stratify patient cohorts","FS Roque, PB Jensen, H Schmock","PLoS Computational Biology","2011","388","https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1002141"),
("D_association_rule_clinical","Research on basic clinical treatment pattern mining based on EMR big data","Q Lu, X Zheng, J Chen","IEEE","2023","1","https://ieeexplore.ieee.org/abstract/document/10104953/"),
("D_association_rule_clinical","Rule mining and sequential pattern based predictive modeling with EMR data","O Abar","University of Kentucky Thesis","2019","1","https://uknowledge.uky.edu/cs_etds/85/"),
("D_association_rule_clinical","Temporal data mining in EMR from patients with acute coronary syndrome","W Black","University of Washington","2014","3",""),
("D_association_rule_clinical","Hidden pattern discovery on clinical data: an approach based on data mining techniques","M Roostaee, R Meidanshahi","Journal of AI and Data Mining","2023","10","https://jad.shahroodut.ac.ir/article_2857.html"),
("D_association_rule_clinical","Discriminative probabilistic pattern mining using graph for EHR","E Li","Seoul National University","2019","0","https://s-space.snu.ac.kr/handle/10371/161070"),
("D_association_rule_clinical","Exploring the predictive factors of heart disease using rare association rule mining","S Darrab, D Broneske, G Saake","Scientific Reports","2024","25","https://www.nature.com/articles/s41598-024-69071-6"),
("D_association_rule_clinical","Combining unsupervised supervised and rule-based algorithms for text mining of EHR","GT Berge, OC Granmo, TO Tveit","ISD 2017","2017","10","https://aisel.aisnet.org/isd2014/proceedings2017/CogScience/2/"),
("D_association_rule_clinical","Temporal pattern discovery in longitudinal electronic patient records","GN Noren, J Hopstadius, A Bate, K Star","Data Mining and Knowledge Discovery","2010","228","https://link.springer.com/article/10.1007/s10618-009-0152-3"),
("D_association_rule_clinical","Patterns of multimorbidity and functional status using cluster analysis and association rule mining","M Provinciali, R Lisa, AR Bonfigli, E Filicetti","Journal of Translational Medicine","2024","14","https://link.springer.com/article/10.1186/s12967-024-05444-9"),
("D_association_rule_clinical","Temporal condition pattern mining in large sparse EHR data: pediatric asthma","EA Campbell, EJ Bass, AJ Masino","JAMIA","2020","18","https://academic.oup.com/jamia/article-abstract/27/4/558/5734732"),
("D_association_rule_clinical","Combining unsupervised supervised and rule-based learning: detecting patient allergies in EHR","GT Berge, OC Granmo, TO Tveit, AL Ruthjersen","BMC Medical Informatics and Decision Making","2023","52","https://link.springer.com/article/10.1186/s12911-023-02271-8"),
("D_association_rule_clinical","Textual analysis and visualization of research trends in data mining for EHR","J Chen, W Wei, C Guo, L Tang, L Sun","Health Policy and Technology","2017","52","https://www.sciencedirect.com/science/article/pii/S2211883717300692"),
# ── Cluster E: automatic MCQ generation ──
("E_automatic_mcq_generation","MCQG-SRefine: MCQ generation and evaluation with iterative self-critique correction and comparison","Z Yao, A Parashar, H Zhou, WS Jang","NAACL 2025","2025","38","https://aclanthology.org/2025.naacl-long.538/"),
("E_automatic_mcq_generation","The use of LLMs in generating MCQs for health professions education: systematic review and meta-analysis","L Riehm, K Nanji, M Lakhani, E Pankiv, D Hasanee","PLOS ONE","2026","4","https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0340277"),
("E_automatic_mcq_generation","LLM-generated multiple choice practice quizzes for preclinical medical students","T Camarata, L McCoy, R Rosenberg","Advances in Physiology Education","2025","19","https://journals.physiology.org/doi/abs/10.1152/advan.00106.2024"),
("E_automatic_mcq_generation","Automatic generation of medical case-based MCQs: review of methodologies applications evaluation","S Al Shuraiqi, A Aal Abdulsalam, K Masters","Big Data and Cognitive Computing","2024","32","https://www.mdpi.com/2504-2289/8/10/139"),
("E_automatic_mcq_generation","Fine-tuned LLMs for generating MCQs in anesthesiology: psychometric comparison","CR Holzing, C Meynhardt, P Meybohm","JMIR Formative Research","2026","1","https://formative.jmir.org/2026/1/e84904"),
("E_automatic_mcq_generation","LLMs as tools to generate radiology board-style MCQs","NP Mistry, H Saeed, S Rafique, T Le, H Obaid","Academic Radiology","2024","64","https://www.sciencedirect.com/science/article/pii/S107663322400432X"),
("E_automatic_mcq_generation","Docimological quality analysis of LLM-generated MCQs in computer science and medicine","C Grevisse, MAS Pavlou, JG Schneider","SN Computer Science","2024","43","https://link.springer.com/article/10.1007/s42979-024-02963-6"),
("E_automatic_mcq_generation","Leveraging LLMs to generate MCQs for ophthalmology education","S Gholami, DB Mummert, B Wilson, S Page","JAMA Ophthalmology","2025","9","https://jamanetwork.com/journals/jamaophthalmology/article-abstract/2839639"),
("E_automatic_mcq_generation","LLMs can generate high-quality pathology MCQs comparable to human expert","MJ Borowitz, AL Blackford, S Nagelia, RH Hruban","Modern Pathology","2025","4","https://www.sciencedirect.com/science/article/pii/S0893395225002388"),
("E_automatic_mcq_generation","Enhancing clinical MCQ benchmarks with knowledge graph guided distractor generation","R Yang, W Deng, M Chen, Y Zhou, X Li","arXiv:2506.00612","2025","1","https://arxiv.org/abs/2506.00612"),
("E_automatic_mcq_generation","The effects of LLMs on generation of MCQs in medical education: a scoping review","BEA Mohammed, TEA Mohammed","International Journal of Medical Education","2026","0",""),
("E_automatic_mcq_generation","Medical large language models are easily distracted","K Vishwanath, A Alyakin, DA Alber, JV Lee","arXiv:2504.01201","2025","19","https://arxiv.org/abs/2504.01201"),
("E_automatic_mcq_generation","State of the art survey of automatic question generation based on LLMs","OL Abdullah, A Emam, MM Nasef","International Journal of Technology","2026","0","https://ijt.journals.ekb.eg/article_513804.html"),
("E_automatic_mcq_generation","Distractor generation for MCQs with predictive prompting and LLMs","SK Bitew, J Deleu, C Develder, T Demeester","ECIR 2024","2023","54","https://link.springer.com/chapter/10.1007/978-3-031-74627-7_4"),
("E_automatic_mcq_generation","Evaluation of LLM-generated distractors of MCQs for Japanese National Nursing Examination","Y Kido, H Yamada, T Tokunaga, R Kimura, Y Miura","CSEDU 2025","2025","1","https://www.scitepress.org/Papers/2025/134603/134603.pdf"),
("E_automatic_mcq_generation","Exploring automated distractor generation for math MCQs via LLMs","W Feng, J Lee, H McNichols, A Scarlatos","Findings of NAACL 2024","2024","67","https://aclanthology.org/2024.findings-naacl.193/"),
("E_automatic_mcq_generation","Automatic distractor generation in MCQs using LLMs with expert-informed strategies","Y Nagai, M Uto","ICCE 2025","2025","0","https://library.apsce.net/index.php/ICCE/article/view/5928"),
("E_automatic_mcq_generation","LLM-based automatic generation of MCQs with meaningful distractors","VJS Chico, AG Regino, R Bonacin","SBIE 2025","2025","0","https://sol.sbc.org.br/index.php/sbie/article/view/38469"),
("E_automatic_mcq_generation","LLM-generated MCQ practice quizzes for pre-clinical medical students","KR Temprine, K Brettschnieder","Advances in Physiology Education","2025","0","https://journals.physiology.org/doi/prev/20250614-aop/pdf/10.1152/advan.00106.2024"),
# ── Cluster F: benchmark quality leakage ──
("F_benchmark_quality_leakage","LiveMedBench: a contamination-free medical benchmark for LLMs with automated rubric evaluation","Z Yan, D Song, Z Fang, Y Ji, X Li, Q Li, L Sun","arXiv:2602.10367","2026","9","https://arxiv.org/abs/2602.10367"),
("F_benchmark_quality_leakage","LiveClin: a live clinical benchmark without leakage","X Wang, Y Shen, J Chen, J Wang, J Gu","ICLR 2026","2026","3","https://proceedings.iclr.cc/paper_files/paper/2026/hash/9f45b2d4ace7ae425e40c7c1d0d37e64-Abstract-Conference.html"),
("F_benchmark_quality_leakage","A HIPAA-aware benchmark and evaluation harness for clinical LLMs to quantify hallucination bias PHI leakage","V Palama","Well Testing Journal","2025","5",""),
("F_benchmark_quality_leakage","Beyond benchmarks: dynamic automatic and systematic red-teaming agents for trustworthy medical LLMs","J Pan, B Jian, P Hager, Y Zhang, C Liu","arXiv:2508.00923","2025","12","https://arxiv.org/abs/2508.00923"),
("F_benchmark_quality_leakage","Beyond the leaderboard: rethinking medical benchmarks for LLMs","W Wang, Z Ma, G Yu, YF Cheung, M Ding","ACL 2026","2026","15","https://aclanthology.org/2026.acl-long.1996/"),
("F_benchmark_quality_leakage","Clinical LLM evaluation by expert review (CLEVER): framework development and validation","V Kocaman, MA Kaya, AM Feier, D Talby","JMIR AI","2025","25","https://ai.jmir.org/2025/1/e72153/"),
("F_benchmark_quality_leakage","Leak cheat repeat: data contamination and evaluation malpractices in closed-source LLMs","S Balloccu, P Schmidtova, M Lango","EACL 2024","2024","418","https://aclanthology.org/2024.eacl-long.5/"),
("F_benchmark_quality_leakage","Benchmark data contamination of LLMs: a survey","C Xu, S Guan, D Greene, M Kechadi","arXiv:2406.04244","2024","212","https://arxiv.org/abs/2406.04244"),
("F_benchmark_quality_leakage","Contamination in AI evaluation","B Mehrbakhsh","UPV Technical Report","2026","0",""),
("F_benchmark_quality_leakage","Position: the open benchmark paradox must be resolved through sovereign medical evaluation","K Kim, H Ko, H Jo, S Kim, Y Choi, JD Lee","NeurIPS 2025","2025","0","https://openreview.net/forum?id=5QNloNBcyn"),
("F_benchmark_quality_leakage","Training on the benchmark is not all you need","S Ni, X Kong, C Li, X Hu, R Xu, J Zhu","AAAI 2025","2025","48","https://ojs.aaai.org/index.php/AAAI/article/view/34678"),
("F_benchmark_quality_leakage","Simulating training data leakage in MCQ benchmarks for LLM evaluation","NS Hidayat, MD Al Kautsar","Eval4NLP 2025","2025","5","https://aclanthology.org/2025.eval4nlp-1.3/"),
("F_benchmark_quality_leakage","Are LLM benchmarks already contaminated? Systematic review of contamination detection","E Nourbakhsh, MS Sirjani, A Mousavi","GEM 2026","2026","0","https://aclanthology.org/2026.gem-main.50/"),
("F_benchmark_quality_leakage","Generalization or memorization: data contamination and trustworthy evaluation for LLMs","Y Dong, X Jiang, H Liu, Z Jin, B Gu","Findings of ACL 2024","2024","283","https://aclanthology.org/2024.findings-acl.716/"),
("F_benchmark_quality_leakage","A survey on evaluating quality and trustworthiness in LLM-generated data","K Zhang, M Hu, HAD Le, FK Torsha, Z Jiang","arXiv:2601.17717","2026","0","https://arxiv.org/abs/2601.17717"),
("F_benchmark_quality_leakage","Benchmark probing: investigating data leakage in LLMs","C Deng, Y Zhao, X Tang, M Gerstein","NeurIPS 2023 Workshop","2023","44","https://openreview.net/forum?id=a34bgvner1"),
("F_benchmark_quality_leakage","Benchmarking truthfulness metrics in health-oriented LLMs via automated fact verification","K Das, R Singh","IJCHML","2026","0","https://ijchml.com/index.php/ijchml/article/view/257"),
("F_benchmark_quality_leakage","Private benchmarking to prevent contamination and improve comparative evaluation (CONFIDE)","T Rajore, N Chandran, S Sitaram, D Gupta","arXiv:2403.00393","2024","24","https://arxiv.org/abs/2403.00393"),
("F_benchmark_quality_leakage","A survey on medical competence evaluation benchmarks for LLMs","Q Wang, H Zou, H Zhang, Y Huang, J Tian","Health Care Science","2026","2","https://onlinelibrary.wiley.com/doi/abs/10.1002/hcs2.70050"),
("F_benchmark_quality_leakage","Advances evaluation and explainability of LLMs in healthcare: a systematic review","SU Amin, M Guizani, MS Hossain","ACM TOMM","2026","4","https://dl.acm.org/doi/abs/10.1145/3786334"),
]

def normalize_title(t):
    return re.sub(r'[^a-z0-9]', '', t.lower())[:80]

def main():
    # Flatten
    flat = []
    for cluster, title, authors, journal, year, cited, href in RAW:
        flat.append({'cluster': cluster, 'title': title, 'authors': authors,
                     'journal': journal, 'year': year, 'citedBy': cited,
                     'href': href, 'source': 'Google Scholar'})
    print(f"GS raw total: {len(flat)}")

    # Load existing for dedup
    existing_titles = set()
    ep = os.path.join(HERE, 'literature_search_results.json')
    if os.path.exists(ep):
        with open(ep, 'r', encoding='utf-8') as f:
            ex = json.load(f)
        clusters = ex.get('clusters', {})
        for cname, cdata in clusters.items():
            if not isinstance(cdata, dict):
                continue
            for src in ('pubmed', 'arxiv'):
                src_data = cdata.get(src, {})
                recs = src_data.get('records', src_data) if isinstance(src_data, dict) else src_data
                for r in (recs if isinstance(recs, list) else []):
                    if isinstance(r, dict) and 'title' in r:
                        existing_titles.add(normalize_title(r['title']))
        print(f"Existing PubMed+arXiv unique titles: {len(existing_titles)}")

    # Dedup
    seen = set()
    new_records = []
    for r in flat:
        nt = normalize_title(r['title'])
        if nt in existing_titles or nt in seen:
            continue
        seen.add(nt)
        new_records.append(r)
    dup_count = len(flat) - len(new_records)
    print(f"After dedup: {len(new_records)} new ({dup_count} duplicates)")

    # Save
    out = os.path.join(HERE, 'gs_supplementary_results.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'_meta': {'source': 'Google Scholar', 'date': '2026-08-06',
                             'total_raw': len(flat), 'total_new': len(new_records)},
                   'raw': flat, 'new': new_records}, f, indent=2, ensure_ascii=False)
    print(f"Saved: {out}")

    for c in sorted(set(r['cluster'] for r in new_records)):
        n = sum(1 for r in new_records if r['cluster'] == c)
        print(f"  {c}: {n} new")

if __name__ == '__main__':
    main()
