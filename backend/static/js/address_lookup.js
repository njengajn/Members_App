function lookupPostcode() {
    const postcode = document.getElementById("postcode").value;

    if (!postcode) {
        alert("Enter a postcode");
        return;
    }

    fetch(`/api/postcode-lookup/?postcode=${postcode}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                document.getElementById("town").value = data.town || "";
                document.getElementById("county").value = data.county || "";
            } else {
                alert("Postcode not found");
            }
        })
        .catch(() => {
            alert("Error looking up postcode");
        });
}