function handleClick(element) { // funkcija se izvede, ko nekdo klikne na pesem v elementu (tabeli s pesmimi)
    // za pridobivanje podatkov o pesmi
    const pesemId = element.getAttribute("data-id");
    const naslov = element.textContent;
    var potrditev = confirm("Ali ste prepričani, da želite izbrati: " + naslov + "?");
    
    // če je uporabnik pritisnil na "Confirm", se izvede ajax klic, ki pošlje podatke v Flask 
    if (potrditev){
        $.ajax({
            url: "/v_cakalno_vrsto",
            method: "POST",
            contentType: "application/json", 
            data: JSON.stringify({ id: pesemId}), 
            success: function(response) {
                console.log("Uspešno poslal podatke:", response);
                window.location.href = "/zabelezeno";
            },
            error: function(error) {
                console.error("Napaka pri pošiljanju:", error);
            }
        });
    } else {
        console.log("Uporabnik je preklical izbiro.");
    }
}

$(document).ready(function() {
    const totalTime = 2 * 60; // 2 minuti v sekundah
    let timeLeft = totalTime;

    // Posodobi časovnik vsako sekundo
    const timer = setInterval(function() {
        timeLeft--;

        // Posodobi širino časovnega traku
        const percentage = (timeLeft / totalTime) * 100;
        $('#timer-bar').css('width', percentage + '%');

        // Posodobi barvo časovnega traku (od zelene do rdeče)
        const hue = (timeLeft / totalTime) * 120; // HSL odtenek: 120 (zelena) do 0 (rdeča)
        $('#timer-bar').css('background-color', `hsl(${hue}, 100%, 50%)`);

        // Posodobi besedilo časovnika
        const minutes = Math.floor(timeLeft / 60);
        const seconds = timeLeft % 60;
        $('#timer-text').text(`Preostali čas: ${minutes}:${seconds < 10 ? '0' : ''}${seconds}`);

        // Preusmeri, ko čas poteče
        if (timeLeft <= 0) {
            clearInterval(timer);
            alert('Čas je potekel!');
            window.location.href = '/prepozno'; // Preusmeri na domačo stran
        }
    }, 1000); // Zaženi vsako sekundo
});

$(document).on('keydown', function(e) {
    if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
        e.preventDefault();
        alert('Osvežitev ni dovoljena! Časovnik se nadaljuje.');
    }
});