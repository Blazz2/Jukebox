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