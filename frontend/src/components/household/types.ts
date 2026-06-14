// Canoniek datacontract voor het gedeelde gezinsformulier (#125).
// Eén persoon-vorm voor registratie (1), "Mijn gezin" (2) en admin (3).

export interface PersonInput {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender_code: string;
  email: string;
  phone: string;
  mobile: string;
  relation_type: string;
}

// Adres hoort enkel bij het hoofdlid (= het gezinsadres). Overige gezinsleden
// hebben geen eigen adres. Zie #125.
export interface AddressInput {
  street: string;
  house_number: string;
  bus_number: string;
  postal_code: string;
}

export interface PostalOption {
  postal_code: string;
  municipality: string;
}

export const emptyPerson = (relation_type = "HOOFDLID"): PersonInput => ({
  first_name: "", last_name: "", date_of_birth: "", gender_code: "",
  email: "", phone: "", mobile: "", relation_type,
});

export const emptyAddress = (): AddressInput => ({
  street: "", house_number: "", bus_number: "", postal_code: "",
});
