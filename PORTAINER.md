# Portainer Stack - Deploy from GitHub
# In Portainer: Stacks > Add Stack > Repository
# Repository URL: https://github.com/your-username/ia-drive
# Compose path: docker-compose.yml
# This pulls latest code automatically

# Or paste the docker-compose.yml directly in Web Editor

## Portainer Stack Deployment

### Method 1: GitHub Repo (Recommended)
1. Push these files to GitHub: https://github.com/your-username/ia-drive
2. In Portainer: Stacks → Add Stack → Repository
3. Repository URL: `https://github.com/your-username/ia-drive`
4. Compose path: `docker-compose.yml`
5. Add environment variables in Portainer
6. Deploy

### Method 2: Web Editor
Copy the contents of `docker-compose.yml` into Portainer Stack Web Editor.

Environment variables to set:
- IA_ACCESS_KEY
- IA_SECRET_KEY
- WORKER_MEDIA_BASE
- LOGIN_PIN=2580
