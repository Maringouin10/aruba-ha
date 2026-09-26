# Aruba HA — intégration Home Assistant pour HP Aruba 2930F (JL260A)

Intégration personnalisée (HACS) pour superviser et piloter un switch **HP Aruba
2930F 48G PoE+ (JL260A)** — ou tout autre switch **ArubaOS-Switch** compatible —
depuis Home Assistant, via **SNMP** (v2c ou v3).

## Fonctionnalités

- **Capteurs système** : nom, description, uptime du switch.
- **Santé matérielle** : utilisation CPU (%), utilisation mémoire (%),
  température(s) (°C, une entité par sonde), état de chaque ventilateur/capteur
  matériel et de chaque alimentation (bloc d'alimentation) — en `binary_sensor`
  de type "problème" (allumé = anomalie détectée).
- **Par port** : état du lien (up/down), octets reçus/envoyés (compteurs 64 bits),
  vitesse négociée, adresse MAC.
- **PoE** : port sous tension ou non, classe de puissance, puissance totale
  consommée, et puissance réelle par port (MIB constructeur `HP-ICF-POE-MIB`,
  objet `hpicfPoePethPsePortActualPower`).
- **Contrôle des ports** (optionnel) : une entité `switch` par port pour
  l'activer/le désactiver à distance (ex. redémarrer un appareil POE en
  coupant son port).
- **Suivi des appareils connectés** (optionnel) : une entité `device_tracker`
  par adresse MAC apprise dans la table CAM du switch, avec le port associé.

Tout est interrogé en une seule intégration, sans fichier MIB à compiler —
uniquement des OID numériques (MIB standards IF-MIB/POWER-ETHERNET-MIB/
BRIDGE-MIB, plus les MIB constructeur HP-ICF-CHASSIS/STATISTICS-MIB/
NETSWITCH-MIB/HP-ICF-POE-MIB pour la santé matérielle et le PoE détaillé,
dont les OID ont été vérifiés contre les fichiers MIB HP publiés).

## Installation

### Via HACS (recommandé)

1. HACS → menu (⋮) → **Dépôts personnalisés**.
2. Ajouter l'URL de ce dépôt, catégorie **Intégration**.
3. Installer **Aruba HA (2930F / ArubaOS-Switch)**, puis redémarrer Home
   Assistant.

### Manuellement

Copier le dossier `custom_components/aruba_ha` dans le dossier
`custom_components` de votre configuration Home Assistant, puis redémarrer.

## Configuration côté switch

Sur le switch Aruba 2930F (CLI) :

```
configure
snmp-server community "public" operator
snmp-server community "private" manager unrestricted
```

- `operator` = lecture seule (community de **lecture**).
- `manager` = lecture/écriture (community d'**écriture**, nécessaire
  uniquement si vous activez le contrôle des ports).

Pour SNMPv3 (recommandé, plus sécurisé) :

```
configure
snmpv3 enable
snmpv3 user "ha-user" auth sha "motdepasse-auth" priv aes "motdepasse-priv"
snmpv3 group manager user "ha-user" sec-model ver3
```

Adaptez selon votre politique de sécurité (droits `operator` si vous ne voulez
pas activer le contrôle des ports depuis HA).

## Configuration dans Home Assistant

Paramètres → Appareils et services → Ajouter une intégration → **Aruba HA**,
puis suivez l'assistant :

1. Adresse IP/hôte, port SNMP (161 par défaut), version SNMP.
2. Identifiants SNMPv2c (community read/write) ou SNMPv3 (utilisateur,
   auth, priv).
3. Fonctionnalités : contrôle des ports, suivi des appareils, intervalle
   d'interrogation (30 s par défaut).

Ces options peuvent être modifiées ensuite via le bouton **Configurer** de
l'intégration.

## Notes importantes

- Le contrôle des ports effectue un `SNMP SET` sur `ifAdminStatus`. Soyez
  prudent : désactiver le port par lequel transite votre connexion à Home
  Assistant vous couperait l'accès.
- Les capteurs de santé matérielle (CPU, mémoire, ventilateurs, alimentations,
  température) utilisent des MIB propriétaires HP/Aruba (`HP-ICF-CHASSIS`,
  `STATISTICS-MIB`, `NETSWITCH-MIB`, `HP-ICF-POE-MIB`). Elles sont présentes
  sur la quasi-totalité des switches ArubaOS-Switch (2530/2540/2620/2920/2930…)
  mais si une entité n'apparaît pas, c'est que votre firmware n'expose pas cet
  OID précis — les autres capteurs restent disponibles.
- Le suivi des appareils connectés se base sur la table d'adresses MAC du
  switch (Bridge-MIB) : il indique la présence et le port, pas l'adresse IP.
