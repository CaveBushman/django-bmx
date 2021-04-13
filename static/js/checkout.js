    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    // Create an instance of the Stripe object with your publishable API key
    // var stripe = Stripe( "{{ STRIPE_PUBLIC_KEY }}");
    var stripe = Stripe( "pk_test_51HeoE0F3rP8tXY4Cx7YEpcx0fSAQ6M3HYdQrTgiUlNqSxNxCAMbsDBUQt37DCFtDiZLS6sgExG3VDahuc8TEWRF600jwWQ7znp");
    var checkoutButton = document.getElementById("checkout-button");
    checkoutButton.addEventListener("click", function () {
        console.log("Stisknuto tlačítko Zaplatit");
        console.log(stripe);
      fetch("/event/confirm", {
        method: "POST",
        headers: {
          'X-CSRFToken': csrftoken
        }
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (session) {
          return stripe.redirectToCheckout({ sessionId: session.id });
        })
        .then(function (result) {
          // If redirectToCheckout fails due to a browser or network
          // error, you should display the localized error message to your
          // customer using error.message.
          if (result.error) {
            alert(result.error.message);
          }
        })
        .catch(function (error) {
          console.error("Error:", error);
        });
    });