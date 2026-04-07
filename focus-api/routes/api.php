<?php

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;
use App\Models\Entry;

Route::get('/entries', function () {
    return Entry::latest()->get();
});

Route::post('/entries', function (Request $request) {
    $request->validate([
        'title' => 'required',
        'focus_level' => 'required|integer|min:1|max:3'
    ]);

    return Entry::create($request->all());
});