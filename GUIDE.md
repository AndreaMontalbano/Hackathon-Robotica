# Linea Guida Tecnica — SO-101 Mirror Arm

> Documento interno. Spiega le decisioni architetturali, i punti critici, e come
> evolvere il progetto oltre l'hackathon.

---

## Architettura in 3 parole

**Capture → Map → Send.**

Ogni frame della camera passa attraverso tre moduli indipendenti. Puoi sostituire
ognuno senza toccare gli altri.

---

## Flusso dati dettagliato

```
frame BGR
    │
    ▼
PoseTracker.process(frame)
    │  usa MediaPipe Pose + Hands
    │  output: ArmLandmarks (shoulder, elbow, wrist, index_tip, thumb_tip)
    │
    ▼
JointMapper.map(landmarks)
    │  calcola angoli geometrici in gradi
    │  applica smoothing esponenziale
    │  clamp ai limiti fisici del SO-101
    │  output: Dict{"1": 23.4, "2": -12.1, ..., "6": 67.0}
    │
    ▼
RobotController.send_joints(angles)
    │  chiama arm.set_joint(id, angle) per ogni giunto
    │  modalità dry_run: stampa a console
    │  modalità simulation: digital twin Cyberwave
    │  modalità real: hardware fisico
    ▼
SO-101
```

---

## I 6 giunti del SO-101 e come li calcoliamo

| Giunto | Nome | Come lo deriviamo |
|--------|------|-------------------|
| "1" | Shoulder Pan | arctan2 di (elbow.x - shoulder.x, -(elbow.y - shoulder.y)) |
| "2" | Shoulder Tilt | angolo verticale del braccio superiore rispetto al riferimento T-pose |
| "3" | Elbow Flex | angolo tra vettore spalla→gomito e gomito→polso (law of cosines) |
| "4" | Wrist Flex | direzione verticale dell'avambraccio |
| "5" | Wrist Roll | differenza di profondità z tra polso e gomito (proxy — impreciso) |
| "6" | Gripper | distanza normalizzata tra punta indice e pollice |

### Cosa è preciso e cosa no

- **Preciso**: J1 (pan), J3 (elbow flex), J6 (gripper) — derivati da geometria 2D pulita.
- **Accettabile**: J2 (tilt), J4 (wrist flex) — dipendono dal piano di ripresa.
- **Proxy grezzo**: J5 (wrist roll) — MediaPipe dà z normalizzato, non profondità metrica. Migliorabile con RealSense o IMU sul polso.

---

## Calibrazione — perché è necessaria

MediaPipe dà coordinate normalizzate nell'immagine (0–1). La posizione della spalla
cambia in base a dove la persona è inquadrata. La calibrazione in T-pose registra
`shoulder.y` come riferimento, così "braccio giù" = 0° anche se la persona è
decentrata rispetto alla camera.

**Rifare sempre la calibrazione se:**
- La persona si avvicina o allontana dalla camera
- La camera viene spostata
- Diversa persona usa il sistema

---

## Smoothing esponenziale

```
angle_smoothed[t] = α * angle_smoothed[t-1] + (1-α) * angle_raw[t]
```

`α = 0.4` è il default. Valori più alti = più fluido ma più lento a rispondere.
Per una demo dal vivo usa `--smooth 0.5`. Per massima reattività usa `--smooth 0.1`.

---

## Modalità operative

### dry_run
Nessuna dipendenza da Cyberwave. Stampa gli angoli a console. Usa questa per:
- Testare il mapper senza robot
- Debug del pose tracker
- CI/CD e unit test

### simulation
Richiede account Cyberwave attivo. Controlla il digital twin — puoi vedere il robot
muoversi nell'interfaccia web di Cyberwave senza toccare hardware.
**Usa questa per dimostrare il progetto all'hackathon se non hai il robot fisico.**

### real
Richiede `cyberwave pair` già eseguito. Controlla il robot fisico. Inizia sempre
lento (`--fps 10`) e aumenta dopo aver verificato che il mapping sia corretto.

---

## Ordine di sviluppo consigliato

```
1. python demo/demo_sim.py          → verifica che il codice giri
2. python -m pytest tests/           → verifica il mapper matematicamente
3. python src/main.py --mode dry_run --debug  → verifica il pose tracking live
4. python src/main.py --mode simulation --debug  → verifica sul twin
5. python src/main.py --mode real    → hardware fisico, movimenti lenti
```

Non passare al passo successivo finché quello corrente non è stabile.

---

## Punti critici da calibrare sul robot fisico

### 1. Range dei giunti
I limiti in `config/so101.yaml` e `joint_mapper.py` sono stime conservative.
Dopo aver connesso il robot reale, muovilo manualmente agli estremi e aggiorna i valori.

### 2. Home position
Il robot va in home (J3=90°, resto=0°) all'avvio e allo shutdown. Verifica che
questa posizione sia sicura per il tuo setup fisico (niente che il braccio possa colpire).

### 3. Velocità di aggiornamento
Il default è 30 fps. Se il robot ha lag o movimenti bruschi, riduci a 15 fps
(`--fps 15`) e aumenta lo smoothing (`--smooth 0.6`).

---

## Come evolvere oltre l'hackathon

### A breve termine
- **Profondità reale per J5**: aggiungi una Intel RealSense D435 o simile.
  MediaPipe ha un modello World che dà coordinate metriche se calibrato.
- **Filtro Kalman**: sostituisci lo smoothing esponenziale con un filtro Kalman
  per predire il movimento e ridurre il lag percepito.

### A medio termine
- **Raccolta dati**: usa `cyberwave record` per salvare dimostrazioni.
  Il formato LeRobot è già compatibile con HuggingFace LeRobot.
- **Policy model**: allena un modello di imitazione sulle dimostrazioni registrate.
  Cyberwave ha un catalogo di policy models e supporta il fine-tuning.
- **Teleoperation bidirezionale**: aggiungi feedback aptico (vibrazione al polso)
  quando il robot raggiunge i limiti fisici.

### A lungo termine
- Sostituisci MediaPipe con un modello 3D body estimation (ad esempio HaMeR per le mani)
  per avere dati di posizione assoluta invece di angoli relativi all'immagine.

---

## Struttura file — dove mettere mano

| Cosa vuoi cambiare | File da modificare |
|--------------------|-------------------|
| Aggiungere un giunto | `joint_mapper.py` → `_compute()` e `JOINT_LIMITS` |
| Cambiare i limiti fisici | `config/so101.yaml` e `joint_mapper.py` |
| Usare un altro robot | `robot_controller.py` → metodi connect/send |
| Migliorare il pose tracking | `pose_tracker.py` → sostituisci MediaPipe |
| Cambiare smoothing default | `config/so101.yaml` → `pose_tracker.smoothing` |
| Aggiungere una GUI | crea `src/ui.py` che importa gli stessi moduli |

---

## FAQ

**Q: Il braccio si muove in modo invertito (destra/sinistra scambiati)?**
Il frame è flippato per la vista selfie. Se il robot è dall'altra parte della camera
rispetto a te, rimuovi il `cv2.flip(frame, 1)` in `main.py`.

**Q: MediaPipe non rileva la pose?**
- Assicurati di avere buona illuminazione
- Il braccio intero (spalla → polso) deve essere visibile
- Prova `--confidence 0.5` (valore più basso = meno restrittivo)

**Q: Il robot va in posizione strana all'avvio?**
La home è hardcoded in `robot_controller.py → home()`. Modifica i valori
dopo aver capito la zero-position del tuo robot specifico.

**Q: Come faccio a registrare una demo video per GitHub?**
```bash
# Lancia con --debug per il window con skeleton, poi usa OBS o ffmpeg per catturare
python src/main.py --mode simulation --debug
```
