function toggleContent() {
      const blocBody = document.getElementById("blocBody");
      const btn = document.querySelector(".toggle-btn");

      if (blocBody.style.display === "none" || blocBody.style.display === "") {
        blocBody.style.display = "block";
        btn.textContent = "Afficher moins";
      } else {
        blocBody.style.display = "none";
        btn.textContent = "Afficher plus";
      }
    }