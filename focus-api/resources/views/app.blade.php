<!DOCTYPE html>
<html>
<head>
    <title>FocusFlow</title>
    <style>
        body {
            font-family: Arial;
            background: #111;
            color: white;
            padding: 20px;
        }
        input, select, button {
            padding: 10px;
            margin: 5px;
        }
        .card {
            background: #222;
            padding: 10px;
            margin: 10px 0;
            border-radius: 8px;
        }
    </style>
</head>
<body>

<h1>🔥 FocusFlow</h1>

<input id="title" placeholder="Wat heb je gedaan?">
<select id="focus">
    <option value="1"> Slecht</option>
    <option value="2"> Oke</option>
    <option value="3"> Top</option>
</select>
<button onclick="addEntry()">Toevoegen</button>

<div id="list"></div>

<script>
async function loadEntries() {
    const res = await fetch('/entries');
    const data = await res.json();

    const list = document.getElementById('list');
    list.innerHTML = '';

    data.forEach(e => {
        let emoji = "😐";
        if (e.focus_level == 1) emoji = "😴";
        if (e.focus_level == 3) emoji = "🔥";

        list.innerHTML += `
            <div class="card">
                ${e.title} - ${emoji}
            </div>
        `;
    });
}

async function addEntry() {
    const title = document.getElementById('title').value;
    const focus = document.getElementById('focus').value;

    await fetch('/entries', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': '{{ csrf_token() }}'
        },
        body: JSON.stringify({
            title: title,
            focus_level: focus
        })
    });

    document.getElementById('title').value = '';
    loadEntries();
}

loadEntries();
</script>

</body>
</html>