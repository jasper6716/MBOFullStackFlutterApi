public function up()
{
    Schema::create('entries', function (Blueprint $table) {
        $table->id();
        $table->string('title');
        $table->integer('focus_level');
        $table->timestamps();
    });
}