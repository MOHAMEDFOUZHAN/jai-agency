# GitHub Update Guide

This guide explains how to update your GitHub repository with the latest changes from your local project.

## Standard Update Workflow

Follow these steps every time you want to send your local changes to GitHub:

### 1. Check current status (Optional but recommended)
```powershell
git status
```
*   **Purpose:** Shows which files have been modified, deleted, or are new (untracked). It helps you see what is about to be updated.

### 2. Stage your changes
```powershell
git add .
```
*   **Purpose:** Prepares all your changes for the next commit. The dot `.` means "add all files in the current folder".

### 3. Commit your changes
```powershell
git commit -m "Your description of the changes"
```
*   **Purpose:** Saves your staged changes locally with a descriptive message. Replace `"Your description of the changes"` with a short note about what you did (e.g., `"Updated login page design"`).

### 4. Push to GitHub
```powershell
git push origin main
```
*   **Purpose:** Sends your local commits to the online GitHub repository. Once this finishes, your website/code on GitHub will be updated.

---

## Helpful Tips

### Syncing before you start (Pulling)
If you work from multiple computers or if someone else updates the repo, run this **before** you start working:
```powershell
git pull origin main
```
*   **Purpose:** Downloads any changes from GitHub to your local computer so you are working on the latest version.

### Undoing `git add`
If you added something by mistake before committing:
```powershell
git reset
```
