# PC Builder

Modern local PC parts and PC builder app built with React, Vite, Tailwind CSS, Node.js, Express, and SQLite.

## Start

Double-click `start_app.bat`.

The launcher installs Node dependencies when needed, starts the Express API at `http://127.0.0.1:3001`, starts the Vite frontend at `http://127.0.0.1:5173`, and opens the app in your browser.

## Stack

- Frontend: React + Vite + Tailwind CSS
- Backend: Node.js + Express
- Database: `data/pc_builder.sqlite3`

## Features

- Browse matched product groups while keeping each store offer separate.
- Filter by category, store, stock status, and search text.
- Product cards show square images, store badges, all store prices, stock, and actions.
- Best Value Build suggests only valid PC components.
- Suggested build rows show category, thumbnail, product, store, price, stock, and Change/View.
- Save Build, Export CSV, and Export Excel actions.

## Backend Notes

The backend reads the existing SQLite tables and keeps vendor listings as separate rows. Similar products are grouped at the API layer using normalized product signatures, so Nanotek, GameStreet, Tecroot, Disrupt, and future stores can show side-by-side prices without losing the original offer rows.

Build suggestions use strict component categories:

`Processors / CPUs`, `Motherboards`, `RAM`, `Graphics Cards / GPUs`, `SSDs / HDDs`, `Power Supplies`, `Casing`, `Coolers`

Accessories, posters, holders, brackets, mounts, stands, cables, external enclosures, and non-component products are excluded from suggestions.

## Development

```powershell
npm install
npm run server
npm run client
```

Build the frontend:

```powershell
npm run build
```
