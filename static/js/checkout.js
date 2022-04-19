    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    // Create an instance of the Stripe object with your publishable API key
    // var stripe = Stripe( "{{ STRIPE_PUBLIC_KEY }}");
    const stripe = Stripe("pk_test_51KqNPjJlEL6OSOqYRVsjejRnzgpeJErpVUYfTBxaoNTFoGcvbeMEcS60r5yLi6oWnyc84mpsWou8IAEMaPV6NH0I00JGhHeaLm");
    var checkoutButton = document.getElementById("checkout-button");
    checkoutButton.addEventListener("click", function () {
        console.log("STRIPE je " + stripe);
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