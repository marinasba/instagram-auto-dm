# Documentation - Messages Auto Instagram (gariguettes_fr)

## Qu'est-ce que cette app ?

Une automatisation qui envoie des **DM Instagram automatiques** quand quelqu'un commente un **mot-cle** sous un post de @gariguettes_fr. L'app repond aussi au commentaire avec un message aleatoire (ex: "C'est envoye !").

**Alternative gratuite a Manychat.**

---

## Architecture

```
Utilisateur commente "CHARIOT"
        |
Instagram envoie une notification (webhook)
        |
Serveur Python (heberge sur Railway)
        |
    1. Envoie un DM avec le contenu configure
    2. Repond au commentaire ("C'est envoye !")
```

---

## Ou est quoi ?

### 1. Code source - GitHub

- **Repo** : https://github.com/marinasba/instagram-auto-dm
- **Compte GitHub** : marinasba
- **Fichiers importants** :
  - `main.py` - le serveur (webhook + admin + API)
  - `config.json` - mots-cles, messages DM et reponses aux commentaires
  - `requirements.txt` - dependances Python (fastapi, uvicorn, httpx)
  - `Procfile` - commande de lancement pour Railway

### 2. Hebergement - Railway

- **URL du serveur** : https://web-production-e6a42.up.railway.app
- **Compte Railway** : connecte via GitHub (marinasba)
- **Dashboard** : https://railway.app (se connecter avec GitHub)
- **Variables d'environnement** (dans Railway > projet > service > Variables) :
  - `VERIFY_TOKEN` = token de verification du webhook Meta (valeur : `gariguettes_secret_2026`)
  - `ACCESS_TOKEN` = token Instagram API (commence par `IGAAOV9...`, genere depuis Meta Developer)
  - `ADMIN_TOKEN` = si non defini, utilise la meme valeur que VERIFY_TOKEN
- **Deploiement** : automatique a chaque push sur GitHub (branche `main`)

### 3. Meta Developer - Configuration Instagram API

- **URL** : https://developers.facebook.com
- **Compte** : le compte Facebook de Marina (lie au Business Manager "Gariguettes")
- **Nom de l'app** : "Messages auto"
- **App ID** : 1445863310917375
- **Compte Instagram connecte** : gariguettes_fr (ID: 17841447700219621)
- **Permissions utilisees** :
  - `instagram_business_basic` - acces de base au compte
  - `instagram_manage_comments` - lecture des commentaires
  - `instagram_business_manage_messages` - envoi de DM
- **Webhook configure** :
  - URL de rappel : `https://web-production-e6a42.up.railway.app/webhook`
  - Verify token : `gariguettes_secret_2026`
  - Abonnement : commentaires active sur gariguettes_fr
- **Statut App Review** : en cours (etape 5 "Controle app")

---

## URLs utiles

| Quoi | URL |
|------|-----|
| Interface admin | https://web-production-e6a42.up.railway.app/admin?token=gariguettes_secret_2026 |
| Logs (debug) | https://web-production-e6a42.up.railway.app/logs?token=gariguettes_secret_2026 |
| Politique de confidentialite | https://web-production-e6a42.up.railway.app/privacy |
| Statut serveur | https://web-production-e6a42.up.railway.app/ |
| Dashboard Railway | https://railway.app |
| Dashboard Meta Developer | https://developers.facebook.com |
| Repo GitHub | https://github.com/marinasba/instagram-auto-dm |

---

## Comment gerer les mots-cles et messages (au quotidien)

### Via l'interface admin (le plus simple)

1. Ouvrir : https://web-production-e6a42.up.railway.app/admin?token=gariguettes_secret_2026
2. **Ajouter un mot-cle** : cliquer "+ Ajouter un mot-cle", taper le mot, puis ecrire le message DM
3. **Modifier un message** : editer directement dans le champ texte
4. **Supprimer un mot-cle** : cliquer "Supprimer"
5. **Gerer les reponses aux commentaires** : ajouter/modifier/supprimer les reponses en bas de page (elles tournent aleatoirement)
6. Cliquer **"Enregistrer"**

### Via le code (pour les devs)

1. Modifier `config.json` dans le repo GitHub
2. Push sur `main` > Railway redeploie automatiquement

---

## Comment renouveler le token Instagram

Le token Instagram expire. Quand l'app arrete de fonctionner :

1. Aller sur https://developers.facebook.com > app "Messages auto"
2. Cas d'utilisation > Personnaliser > Etape 2
3. Cliquer "Generer un token" a cote de gariguettes_fr
4. Copier le nouveau token
5. Aller sur Railway > projet > service > Variables
6. Remplacer la valeur de `ACCESS_TOKEN` par le nouveau token
7. Railway redeploie automatiquement

---

## Comment donner acces a un collegue

### Acces a l'admin (gerer les mots-cles)
Partager ce lien : `https://web-production-e6a42.up.railway.app/admin?token=gariguettes_secret_2026`

### Acces au code (modifier l'app)
1. L'ajouter comme collaborateur sur GitHub : https://github.com/marinasba/instagram-auto-dm/settings/access
2. L'ajouter comme membre sur Railway : dashboard Railway > Settings > Members

### Acces a Meta Developer (gerer les permissions/tokens)
1. Aller sur https://developers.facebook.com > app "Messages auto"
2. Roles dans l'application > Roles > Ajouter des personnes
3. L'ajouter en tant que "Developpeur" ou "Admin"

---

## Depannage

### L'app ne repond plus aux commentaires
1. Verifier que le serveur tourne : ouvrir https://web-production-e6a42.up.railway.app/ (doit afficher `{"status":"ok"}`)
2. Verifier les logs : https://web-production-e6a42.up.railway.app/logs?token=gariguettes_secret_2026
3. Si les logs sont vides `[]` > Meta n'envoie pas les webhooks > verifier sur Meta Developer que l'abonnement webhooks est active
4. Si les logs montrent des evenements mais pas de DM > le token a probablement expire > le renouveler (voir section ci-dessus)

### Le serveur a crashe sur Railway
1. Aller sur Railway > projet > service > Deployments
2. Verifier les logs de deploiement
3. Cliquer "Restart" si besoin

### Erreur "Role de developpeur insuffisant" sur Meta
1. Aller sur l'app Meta > Roles dans l'application > Roles
2. Verifier que gariguettes_fr a le role "Testeur(se) Instagram"
3. Si l'invitation est "En attente" : aller sur Instagram > Parametres > Site web > Applications et sites Web > accepter l'invitation

---

## Couts et limitations

### Railway (hebergement)
- **Essai gratuit** : $5 de credits offerts au depart
- **Apres l'essai** : plan Hobby a **$5/mois** + usage (pour notre app le usage est quasi nul, donc ~$5/mois max)
- **Pas de limite** de nombre de requetes ou de contacts
- **Comparaison** : Manychat = $14-29/mois avec limites de contacts. Railway = ~$5/mois sans limites

### Instagram API (Meta)
- **100% gratuit** : aucun cout par message, par commentaire ou par contact
- **Pas de limite** de messages envoyes
- **Seule contrainte** : le token d'acces expire periodiquement, il faut le renouveler (voir section dediee)

### GitHub
- **Gratuit** pour les repos publics (notre cas)
- Si on veut passer en repo prive : gratuit aussi (GitHub Free inclut les repos prives)

### Resume des couts

| Service | Cout | Limites |
|---------|------|---------|
| Railway | ~$5/mois | Aucune limite de contacts |
| Instagram API | Gratuit | Aucune |
| GitHub | Gratuit | Aucune |
| **Total** | **~$5/mois** | **vs Manychat $14-29/mois** |

---

## Stack technique

- **Langage** : Python 3
- **Framework** : FastAPI
- **Serveur** : Uvicorn
- **HTTP client** : httpx (appels vers l'API Instagram)
- **Hebergement** : Railway (~$5/mois)
- **API** : Instagram Graph API v21.0
- **Repo** : GitHub
