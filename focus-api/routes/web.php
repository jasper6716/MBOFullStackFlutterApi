use Illuminate\Http\Request;
use App\Models\Entry;

Route::get('/', function () {
    return view('app');
});

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