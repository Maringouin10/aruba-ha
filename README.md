# Aruba HA — intégration Home Assistant pour HP Aruba 2930F (JL260A)

Intégration personnalisée (HACS) pour superviser et piloter un switch **HP Aruba
2930F 48G PoE+ (JL260A)** — ou tout autre switch **ArubaOS-Switch** compatible —
depuis Home Assistant, via **SNMP** (v2c ou v3).

## Fonctionnalités

- **Capteurs système** : nom, description, uptime du switch.
- **Par port** : état du lien (up/down), octets reçus/envoyés (compteurs 64 bits),
  vitesse négociée, adresse MAC.
- **PoE** : port sous tension ou non, classe de puissance, puissance totale
  consommée, et puissance par port si le firmware l'expose (best-effort, MIB
  constructeur).
- **Contrôle des ports** (optionnel) : une entité `switch` par port pour
  l'activer/le désactiver à distance (ex. redémarrer un appareil POE en
  coupant son port).
- **Suivi des appareils connectés** (optionnel) : une entité `device_tracker`
  par adresse MAC apprise dans la table CAM du switch, avec le port associé.

Tout est interrogé en une seule intégration, sans fichier MIB à compiler
(uniquement des OID numériques standards + une extension constructeur
best-effort pour la puissance PoE par port).

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
- La puissance PoE **par port** en Watts dépend d'une MIB constructeur
  (`HP-ICF-POE-MIB`) qui n'est pas garantie identique sur tous les firmwares.
  Si l'entité n'apparaît pas, seules les informations standard (port sous
  tension, classe de puissance, puissance totale) seront disponibles.
- Le suivi des appareils connectés se base sur la table d'adresses MAC du
  switch (Bridge-MIB) : il indique la présence et le port, pas l'adresse IP.
