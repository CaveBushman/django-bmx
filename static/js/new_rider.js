const uciidEl = document.getElementById('InputUciid')
const firstNameEl = document.getElementById('InputFirstName')
const lastNameEl = document.getElementById('InputLastName')
const dobEl = document.getElementById('InputDateOfBirth')
const emailEl = document.getElementById('InputEmail')
const emergencyContactEl = document.getElementById('InputEmergencyContact')
const emergencyPhoneEl = document.getElementById('InpuEmergencyPhone')
const genderEl = document.getElementById('SelectGender')
const clubEl = document.getElementById('SelectClub')
const plateEl = document.getElementById('SelectFreePlate')

// uciidEl.addEventListener('input', async () => {
//     if(uciidEl.value.length === 11) {
//         const config = {
//             mode:'cors',
//             headers: {
//                 'Content-type': 'application/json; charset=UTF-8',
//                 'Access-Control-Allow-Origin': '*',
//                 "Access-Control-Allow-Methods": "POST, GET, OPTIONS, DELETE, PUT",
//                 "Access-Control-Allow-Headers": "x-requested-with, Content-Type, Origin, authorization, accept, client-security-token"
//             },
//         }
//         console.log(config);
//         const res = await fetch(`https://ucibws.uci.ch/api/contacts/riders?filter.uciid=10047310722`, config)
//         console.log(res);
//         const data = await res.json();
//         console.log(data);
//     }
// })


uciidEl.addEventListener('input', async () => {
    
res = fetch ("https://ucibws.uci.ch/api/contacts/riders?filter.uciid=10047310722", {headers: {'Content-type': 'application/json; charset=UTF-8', 'Access-Control-Allow-Origin': '*', "Access-Control-Allow-Headers": "x-requested-with, Content-Type, Origin, authorization, Accept, client-security-token"}, mode: 'cors'}).
then ((response) => {
    return response.json()
  })
  .then((data) => {
    // Work with JSON data here
    console.log(data)
  })
  .catch((err) => {
    // Do something for an error here
  })
}
)
