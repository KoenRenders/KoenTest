"""The frozen offenders of the CR-13 gate (`tests/test_rules_gate.py`, §B9.3).

**A burn-down, not an exemption list** (§B9.4). Phase 0 froze today's offenders
per gate; every later phase removes the entries of the domains it migrates and
makes the gate hard for them; phase 4 deletes this file. An entry may only
disappear — the gate turns red on a new offender, and on an entry that no longer
occurs.

**Keys carry no line numbers:** they would shift on the first unrelated edit, and
a gate that turns red for the wrong reason gets switched off. Each key names the
thing it is about — `file::function`, `package:piece`, `METHOD path` — so the
commit that changes the type of that thing can find and settle its entries in
the same commit (§B9.3, the #1268 lesson).

Measured by the collectors themselves on `master` of 28 September 2026 (after
#781), not written by hand.
"""

# Empty since CR-13 phase 4: the poster and info-file helpers of activities/models.py
# are read-only relationships now, batch-loaded with the activity list.
SESSION_ON_ENTITY: frozenset[str] = frozenset()


# Empty since CR-13 phase 4: audit got its shape (no lists, no tables of its own,
# said so in its files), stt moved under chatbot (an adapter belongs under the domain
# that uses it), and every other package got the piece it missed.
MODULE_SHAPE: frozenset[str] = frozenset()


# Empty since CR-13 phase 4: the one handler that committed (`on_mail_requested`,
# through _dispatch → _send → _log_email) queues a job now (§B4.1).
COMMIT_IN_HANDLER: frozenset[str] = frozenset()


# Empty since CR-13 phase 4: the same handler no longer sends over SMTP.
NETWORK_IN_HANDLER: frozenset[str] = frozenset()


# Every /api/v1 route (method × path) as of 28 September 2026: none is named
# under ## Callers in a CONTRACT.md yet. Phase 4 names each remaining route or removes
# it (R14), measured in the repository and in the PROD access log.
JSON_ROUTE_WITHOUT_CALLER: frozenset[str] = frozenset(
    {
        "DELETE /api/v1/auth/api-keys/{key_id}",
        "DELETE /api/v1/users/{user_id}",
        "GET /api/v1/admin/pages",
        "GET /api/v1/auth/api-keys",
        "GET /api/v1/auth/me",
        "GET /api/v1/auth/member/me",
        "GET /api/v1/auth/verify-login",
        "GET /api/v1/blocks/{slug}",
        "GET /api/v1/pages",
        "GET /api/v1/pages/{slug}",
        "GET /api/v1/users",
        "POST /api/v1/auth/api-keys",
        "POST /api/v1/auth/request-login",
        "POST /api/v1/auth/verify-otp",
        "POST /api/v1/pages",
        "POST /api/v1/users",
    }
)


# Every Dutch identifier as of 29 September 2026, measured by the word list in
# test_rules_gate.py (#780): 280 def/class names, 148 test file names, 7 migration
# names, 2 module names, no model column. Not renamed (`CLAUDE.md`, *Code language*):
# an entry leaves when its code is rewritten for another reason. A false positive is
# fixed in the word list, never here.
DUTCH_IDENTIFIERS: frozenset[str] = frozenset(
    {
        "config.py::_leeg_is_niet_gezet",
        "domains/activities/admin_ui.py::_lijst_ctx",
        "domains/activities/admin_ui.py::activiteit_aanmaken",
        "domains/activities/admin_ui.py::activiteit_bijwerken",
        "domains/activities/admin_ui.py::activiteit_inschrijvingen_tab",
        "domains/activities/admin_ui.py::activiteit_nieuw",
        "domains/activities/admin_ui.py::activiteit_verwijderen",
        "domains/activities/admin_ui.py::admin_activiteit_detail",
        "domains/activities/admin_ui.py::admin_activiteiten",
        "domains/activities/admin_ui.py::inschrijving_detail",
        "domains/activities/admin_ui.py::inschrijving_nieuw",
        "domains/activities/admin_ui.py::inschrijving_nieuw_opslaan",
        "domains/activities/admin_ui.py::inschrijving_nieuw_prijzen",
        "domains/activities/admin_ui.py::inschrijving_nieuw_totaal",
        "domains/activities/admin_ui.py::inschrijving_opmerking",
        "domains/activities/admin_ui.py::inschrijving_opslaan",
        "domains/activities/admin_ui.py::inschrijving_pagina",
        "domains/activities/admin_ui.py::inschrijving_regel_bijwerken",
        "domains/activities/admin_ui.py::inschrijving_totaal",
        "domains/activities/admin_ui.py::inschrijving_verwijderen",
        "domains/activities/admin_ui.py::onderdeel_export",
        "domains/activities/admin_ui.py::organisatoren_zoeken",
        "domains/activities/router.py::_inschrijver",
        "domains/activities/service.py::_controleer_afrekening",
        "domains/activities/service.py::_controleer_slug",
        "domains/activities/service.py::_datum",
        "domains/activities/service.py::_regel",
        "domains/activities/service.py::controleer_bestelproduct",
        "domains/activities/service.py::inschrijving_kop_ctx",
        "domains/activities/service.py::inschrijving_tabs",
        "domains/activities/service.py::sorteer_inschrijvingen",
        "domains/activities/totals.py::_betaalbaar",
        "domains/activities/ui.py::_lijst_ctx",
        "domains/activities/ui.py::activiteit_deeplink",
        "domains/activities/ui.py::activiteiten_page",
        "domains/activities/ui.py::inschrijf_form",
        "domains/activities/ui.py::inschrijf_submit",
        "domains/activities/ui.py::inschrijf_totaal",
        "domains/activities/viewmodels.py::AdminActiviteitInschrijvingenView",
        "domains/activities/viewmodels.py::AdminActiviteitenView",
        "domains/activities/viewmodels.py::AdminInschrijvingView",
        "domains/auth/admin_ui.py::_filters_uit",
        "domains/auth/admin_ui.py::_lijst_ctx",
        "domains/auth/admin_ui.py::_lijst_response",
        "domains/auth/admin_ui.py::_platform_rollen_uit",
        "domains/auth/admin_ui.py::_werkruimtes",
        "domains/auth/admin_ui.py::admin_gebruikers",
        "domains/auth/admin_ui.py::gebruiker_aanmaken",
        "domains/auth/admin_ui.py::gebruiker_bijwerken",
        "domains/auth/admin_ui.py::gebruiker_nieuw",
        "domains/auth/admin_ui.py::gebruiker_verwijderen",
        "domains/auth/users.py::_actieve_werkruimte",
        "domains/chatbot/seam.py::_alleen_waarden",
        "domains/chatbot/seam.py::_naamscan_tekst",
        "domains/chatbot/ui.py::ai_context_lijst",
        "domains/chatbot/ui.py::notitie_toevoegen",
        "domains/chatbot/ui.py::raakje_vraag",
        "domains/chatbot/ui.py::rij_bewerken",
        "domains/chatbot/ui.py::rij_toggle",
        "domains/chatbot/ui.py::rij_verwijderen",
        "domains/cms/admin_ui.py::_lijst_ctx",
        "domains/cms/admin_ui.py::admin_paginas",
        "domains/cms/admin_ui.py::pagina_aanmaken",
        "domains/cms/admin_ui.py::pagina_bijwerken",
        "domains/cms/admin_ui.py::pagina_detail",
        "domains/cms/admin_ui.py::pagina_nieuw",
        "domains/cms/admin_ui.py::pagina_verplaatsen",
        "domains/cms/admin_ui.py::pagina_verwijderen",
        "domains/cms/admin_ui.py::pagina_voorbeeld",
        "domains/cms/service.py::verplaats_pagina",
        "domains/cms/ui.py::betaling_geannuleerd",
        "domains/cms/ui.py::betaling_succes",
        "domains/cms/ui.py::cms_pagina",
        "domains/forms/admin_ui.py::_bewerk",
        "domains/forms/admin_ui.py::formulier_aanmaken",
        "domains/forms/admin_ui.py::formulier_afdruk",
        "domains/forms/admin_ui.py::formulier_builder",
        "domains/forms/admin_ui.py::formulier_nieuw",
        "domains/forms/admin_ui.py::formulier_verwijderen",
        "domains/forms/admin_ui.py::formulieren_page",
        "domains/forms/admin_ui.py::instellingen_opslaan",
        "domains/forms/admin_ui.py::inzending_verwijderen",
        "domains/forms/admin_ui.py::inzendingen_export",
        "domains/forms/admin_ui.py::inzendingen_tab",
        "domains/forms/admin_ui.py::optie_bewerken",
        "domains/forms/admin_ui.py::optie_toevoegen",
        "domains/forms/admin_ui.py::optie_verplaatsen",
        "domains/forms/admin_ui.py::optie_verwijderen",
        "domains/forms/admin_ui.py::sectie_bewerken",
        "domains/forms/admin_ui.py::sectie_toevoegen",
        "domains/forms/admin_ui.py::sectie_verplaatsen",
        "domains/forms/admin_ui.py::sectie_verwijderen",
        "domains/forms/admin_ui.py::veld_bewerken",
        "domains/forms/admin_ui.py::veld_toevoegen",
        "domains/forms/admin_ui.py::veld_verplaatsen",
        "domains/forms/admin_ui.py::veld_verwijderen",
        "domains/forms/api.py::submit_bericht",
        "domains/forms/service.py::FormulierFout",
        "domains/forms/service.py::VeldFout",
        "domains/forms/service.py::_sectie_indexen",
        "domains/forms/service.py::_veld",
        "domains/forms/service.py::assert_geen_id_vorm",
        "domains/forms/ui.py::_berichten_form",
        "domains/forms/ui.py::berichten_page",
        "domains/forms/ui.py::berichten_submit",
        "domains/forms/ui.py::formulier_edit_page",
        "domains/forms/ui.py::formulier_edit_submit",
        "domains/forms/ui.py::formulier_op_slug",
        "domains/forms/ui.py::formulier_page",
        "domains/forms/ui.py::formulier_submit",
        "domains/mail/service.py::_regel_html",
        "domains/mail/ui.py::_sorteer_labels",
        "domains/mail/ui.py::_sorteer_url",
        "domains/mail/ui.py::email_log_lijst",
        "domains/mail/ui.py::email_log_verwijderen",
        "domains/mdm/import_service.py::_leeg",
        "domains/mdm/ledenrapport.py::build_bestuurslid_index",
        "domains/mdm/ledenrapport.py::read_ledenrapport",
        "domains/mdm/ledenrapport.py::read_ledenrapport_bytes",
        "domains/mdm/organization_service.py::_bewaar_rekening",
        "domains/mdm/organization_service.py::_organisatie",
        "domains/mdm/organization_service.py::_zet_lijstrij",
        "domains/mdm/service.py::_persoon_of_404",
        "domains/mdm/service.py::_waarde",
        "domains/mdm/service.py::gezin_tabs",
        "domains/mdm/tenant_service.py::OngeldigeInstelling",
        "domains/mdm/tenant_service.py::TenantFout",
        "domains/mdm/tenant_service.py::_als_bedrag",
        "domains/mdm/tenant_service.py::_als_geheel",
        "domains/mdm/tenant_service.py::_tekst",
        "domains/mdm/ui.py::_fout",
        "domains/mdm/ui.py::_kaart_response",
        "domains/mdm/ui.py::_lidmaatschapsjaren",
        "domains/mdm/ui.py::_lijst_view",
        "domains/mdm/ui.py::adres_opslaan",
        "domains/mdm/ui.py::bestuurslid_zetten",
        "domains/mdm/ui.py::email_rij",
        "domains/mdm/ui.py::email_toevoegen",
        "domains/mdm/ui.py::email_verwijderen",
        "domains/mdm/ui.py::gezin_aanmaken",
        "domains/mdm/ui.py::gezin_detail",
        "domains/mdm/ui.py::gezin_inschrijvingen_tab",
        "domains/mdm/ui.py::gezin_verwijderen",
        "domains/mdm/ui.py::leden_lijst",
        "domains/mdm/ui.py::leden_page",
        "domains/mdm/ui.py::lid_nieuw",
        "domains/mdm/ui.py::lid_nieuw_persoon_rij",
        "domains/mdm/ui.py::lidmaatschap_toevoegen",
        "domains/mdm/ui.py::lidmaatschap_verwijderen",
        "domains/mdm/ui.py::persoon_opslaan",
        "domains/mdm/ui.py::persoon_toevoegen",
        "domains/mdm/ui.py::persoon_verwijderen",
        "domains/mdm/viewmodels.py::LedenView",
        "domains/media/admin_ui.py::_lijst_ctx",
        "domains/media/admin_ui.py::_lijst_response",
        "domains/media/admin_ui.py::media_bijwerken",
        "domains/media/admin_ui.py::media_nieuw",
        "domains/media/admin_ui.py::media_verplaatsen",
        "domains/media/admin_ui.py::media_verwijderen",
        "domains/media/service.py::MediaFout",
        "domains/media/service.py::controleer_link",
        "domains/media/ui.py::activiteit_fotos",
        "domains/membership/household_service.py::_reconcile_geschrapt_lidmaatschap",
        "domains/membership/schemas_family.py::_hoofdlid_contactgegevens_verplicht",
        "domains/payment/service.py::_bedrag",
        "domains/payment/service.py::_ingetypt_bedrag",
        "domains/payment/service.py::_is_lege_vordering",
        "domains/payment/service.py::_nog_uit_te_betalen",
        "domains/payment/service.py::bevestig_betaling",
        "domains/payment/service.py::bewerk_betaling",
        "domains/payment/service.py::registreer_terugbetaling",
        "domains/payment/service.py::saldo_open",
        "domains/payment/service.py::ververs_betaalstatus",
        "domains/payment/service.py::verwijder_betaling",
        "domains/payment/service.py::zet_betaalstatus",
        "domains/payment/ui.py::_activiteit_scope",
        "domains/payment/ui.py::_gezin_scope",
        "domains/payment/ui.py::_kaart",
        "domains/payment/ui.py::_paginakeuze",
        "domains/payment/ui.py::activiteit_betalingen_tab",
        "domains/payment/ui.py::betaling_bevestigen",
        "domains/payment/ui.py::betaling_bewerken",
        "domains/payment/ui.py::betaling_bijwerken",
        "domains/payment/ui.py::betaling_refund",
        "domains/payment/ui.py::betaling_status",
        "domains/payment/ui.py::betaling_verversen",
        "domains/payment/ui.py::betaling_verwijderen",
        "domains/payment/ui.py::betalingen_export",
        "domains/payment/ui.py::betalingen_lijst",
        "domains/payment/ui.py::betalingen_page",
        "domains/payment/ui.py::gezin_betalingen_tab",
        "domains/payment/ui.py::inschrijving_betalingen_tab",
        "domains/payment/viewmodels.py::BetalingenView",
        "domains/reporting/assistant.py::ScopeNietOverdraagbaar",
        "domains/reporting/assistant.py::_token_voor",
        "domains/reporting/assistant.py::_wat_bestaat_er_wel",
        "domains/reporting/pivot.py::_sleutel",
        "domains/reporting/universe.py::_zet",
        "domains/workflow/ui.py::werkbank_lijst",
        "kernel/geld.py::bedrag",
        "kernel/meetwaarden.py::_datum",
        "kernel/meetwaarden.py::_jaar",
        "kernel/tenant_config.py::_actieve_tenant",
        "kernel/tenant_config.py::_bedrag",
        "kernel/tenant_config.py::_eerste_rekening",
        "kernel/tenant_config.py::_organisatie",
        "kernel/tenant_config.py::_origin_voor",
        "main.py::_StatischeBestanden",
        "migration:044_address_only_on_hoofdlid.py",
        "migration:073_seed_berichten_form.py",
        "migration:074_migrate_ideas_to_berichten.py",
        "migration:092_workflow_subject_id_tekst.py",
        "migration:093_formulier_posities_uniek_per_ouder.py",
        "migration:095_euroteken_voor_de_prijsplaceholder.py",
        "migration:115_reporting_leden_measures.py",
        "module:domains/mdm/ledenrapport.py",
        "module:ui/organisaties_ui.py",
        "test file:test_aanmaken_zonder_modal.py",
        "test file:test_actieve_navigatie.py",
        "test file:test_activiteit_datums_op_eigen_regel.py",
        "test file:test_activiteit_interne_nota.py",
        "test file:test_activiteit_organisatoren.py",
        "test file:test_activiteit_recordpagina.py",
        "test file:test_activiteit_scherm_indeling.py",
        "test file:test_activiteitdetail_verrijking.py",
        "test file:test_activiteiten_editor_623.py",
        "test file:test_activiteiten_keuzelijst.py",
        "test file:test_activiteiten_publiek_ui.py",
        "test file:test_activiteiten_service_crud.py",
        "test file:test_activiteiten_ui.py",
        "test file:test_activiteitkaart_leesmodus.py",
        "test file:test_activiteitspagina_blok_1143.py",
        "test file:test_admin_activiteiten_lijst_ui.py",
        "test file:test_admin_activiteiten_ui.py",
        "test file:test_adresbeheer_portaal.py",
        "test file:test_adresbeheer_scherm.py",
        "test file:test_adresrijen_formulier.py",
        "test file:test_assistant_schermscope.py",
        "test file:test_bedrag_op_de_vernieuwing_1241.py",
        "test file:test_beeldmaat_in_de_editor_1230.py",
        "test file:test_bestuur_maakt_inschrijving_aan.py",
        "test file:test_betaalstatus_tonen.py",
        "test file:test_betaling_fout_toont_de_reden.py",
        "test file:test_betalingen_domeinregels.py",
        "test file:test_betalingen_groepsvolgorde.py",
        "test file:test_betalingen_paginering.py",
        "test file:test_betalingen_scope_overleeft_een_mutatie.py",
        "test file:test_betalingen_ui.py",
        "test file:test_betalingen_zicht_overleeft_een_mutatie.py",
        "test file:test_betalingen_zichten.py",
        "test file:test_betalingenvorm_wijzigingen_emaillog.py",
        "test file:test_bevestig_terugbetaald.py",
        "test file:test_bevestiging_gaat_naar_het_ingevulde_adres.py",
        "test file:test_bewerk_knoppenrij_1090.py",
        "test file:test_bewerken_vervangt_de_leesregel.py",
        "test file:test_bijlage_staat_niet_dubbel.py",
        "test file:test_contactblok_uit_de_organisatie.py",
        "test file:test_contextkaart_terugbetaling.py",
        "test file:test_csrf_token_op_elke_pagina.py",
        "test file:test_deelnemerslijst_na_inschrijving.py",
        "test file:test_deploy_rooktest_wacht.py",
        "test file:test_design_system_pagina.py",
        "test file:test_designs_knop_in_de_recordkop.py",
        "test file:test_email_log_sortering.py",
        "test file:test_filterbalk_op_een_regel.py",
        "test file:test_footer_organisatieblok.py",
        "test file:test_form_instellingen_booleans.py",
        "test file:test_forms_lijst_ui.py",
        "test file:test_formulier_anders_tekst.py",
        "test file:test_formulier_json_rondrit.py",
        "test file:test_formulier_leesbare_link.py",
        "test file:test_formulier_opties_ordenen.py",
        "test file:test_formulier_prefill_ui.py",
        "test file:test_formulier_render.py",
        "test file:test_formulier_sprongbestemming.py",
        "test file:test_formulier_volgorde_tiebreaker.py",
        "test file:test_formulier_vraag_verhuizen.py",
        "test file:test_formulier_vraagtype.py",
        "test file:test_formulierbouwer_iconen.py",
        "test file:test_formulierbouwer_kop.py",
        "test file:test_formulierbouwer_staart.py",
        "test file:test_gate_niet_leeg.py",
        "test file:test_gedeeltelijke_betaling_vereffent_niet.py",
        "test file:test_geen_genest_formulier.py",
        "test file:test_geen_rauwe_codes_op_het_scherm.py",
        "test file:test_gezin_recordpagina.py",
        "test file:test_gezinsportaal_lopende_vernieuwing.py",
        "test file:test_gezinsscherm_deelacties_1111.py",
        "test file:test_golf12_activiteitspagina.py",
        "test file:test_inschrijf_teller.py",
        "test file:test_inschrijfadres_volgt_aanmelding.py",
        "test file:test_inschrijfdatum_per_onderdeel.py",
        "test file:test_inschrijving_contact_corrigeren.py",
        "test file:test_inschrijving_editor_bedragen.py",
        "test file:test_inschrijving_editor_ui.py",
        "test file:test_inschrijving_opslaan_bevestiging.py",
        "test file:test_inschrijving_pagina.py",
        "test file:test_inschrijving_ploegnaam_bewerken.py",
        "test file:test_inschrijving_verplichte_velden.py",
        "test file:test_inschrijvingen_per_onderdeel.py",
        "test file:test_inschrijvingen_per_onderdeel_scherm.py",
        "test file:test_inschrijvingen_sortering.py",
        "test file:test_leden_records_lijst_ui.py",
        "test file:test_leden_ui.py",
        "test file:test_leden_zoeken_op_straat.py",
        "test file:test_ledenexport_volgt_de_periode.py",
        "test file:test_ledenimport_extra_adressen.py",
        "test file:test_ledenimport_wist_niet.py",
        "test file:test_ledenportaal.py",
        "test file:test_ledenrapport_parsing.py",
        "test file:test_ledenwijzigingen_sortering.py",
        "test file:test_lid_aanmaken_een_formulier_1110.py",
        "test file:test_lidgegevens_verplicht.py",
        "test file:test_live_aantal_blijft_staan.py",
        "test file:test_live_totaal_inschrijving.py",
        "test file:test_media_design_soorten.py",
        "test file:test_media_upload_soortkeuze.py",
        "test file:test_meerdere_vorderingen.py",
        "test file:test_meta_regel_uit_de_kit.py",
        "test file:test_migratieketen_gate.py",
        "test file:test_naadwachter_leest_waarden_niet_etiketten.py",
        "test file:test_navigatie_oob_alleen_bij_boost.py",
        "test file:test_nieuwsbrief_alle_adressen.py",
        "test file:test_onderdeel_een_opslaan.py",
        "test file:test_opslaan_bevestiging_schermen.py",
        "test file:test_organisatie_lijsten.py",
        "test file:test_organisatie_opslaan_een_transactie.py",
        "test file:test_organisatie_wereldkenmerken.py",
        "test file:test_organisatiescherm.py",
        "test file:test_paginavolgorde.py",
        "test file:test_penningmeester_door_het_scherm.py",
        "test file:test_product_zichtbaar_label_1201.py",
        "test file:test_publieke_formuliervelden.py",
        "test file:test_publieke_lege_toestanden.py",
        "test file:test_raakje_naam_en_icoon_1117.py",
        "test file:test_raakje_noemt_de_activiteit_1126.py",
        "test file:test_records_lijsten_ui.py",
        "test file:test_refund_weergave.py",
        "test file:test_reporting_activiteitverslag.py",
        "test file:test_reporting_leden_measures.py",
        "test file:test_rollen_per_werkruimte.py",
        "test file:test_scherm_velden.py",
        "test file:test_schermafdruk_zonder_omgevingsbanner.py",
        "test file:test_sectievorm_dient_in_1101.py",
        "test file:test_sorteervolgorde_gelijkstand.py",
        "test file:test_statische_versies.py",
        "test file:test_stille_fout_zichtbaar.py",
        "test file:test_sweep_sluit_taken.py",
        "test file:test_tenant_bedragen.py",
        "test file:test_tenant_beheer.py",
        "test file:test_terugbetaling_kaarten.py",
        "test file:test_vergadering_routes.py",
        "test file:test_vergaderingen.py",
        "test file:test_verplicht_sterretje.py",
        "test file:test_vraagtypografie.py",
        "test file:test_werkbank_betaalkaart.py",
        "test file:test_werkbank_doel.py",
        "test file:test_wijzigingen_scherm.py",
        "test file:test_word_lid_email_rows.py",
        "test file:test_zoek_personen.py",
        "ui/__init__.py::_beheer_account",
        "ui/__init__.py::_footer_organisatie",
        "ui/__init__.py::_gezinslabel",
        "ui/__init__.py::_maandkort",
        "ui/__init__.py::_werkruimte_naam",
        "ui/__init__.py::statisch",
        "ui/__init__.py::statisch_hash",
        "ui/changes_ui.py::_sleutel",
        "ui/changes_ui.py::_sorteer_labels",
        "ui/changes_ui.py::_sorteer_url",
        "ui/changes_ui.py::admin_ledenwijzigingen",
        "ui/changes_ui.py::ledenwijzigingen_export",
        "ui/changes_ui.py::wijzigingen_ctx",
        "ui/design_system_ui.py::_iconen",
        "ui/organisaties_ui.py::_lijst_ctx",
        "ui/organisaties_ui.py::organisatie_editor",
        "ui/organisaties_ui.py::organisatie_opslaan",
        "ui/organisaties_ui.py::organisaties",
        "ui/system_ui.py::_mijn_werkruimtes",
        "ui/system_ui.py::_toon",
        "ui/system_ui.py::_werkruimte_namen",
        "ui/system_ui.py::admin_werkruimte_wisselen",
        "ui/tenants_ui.py::_lijst_ctx",
        "ui/tenants_ui.py::tenant_aanmaken",
        "ui/tenants_ui.py::tenant_nieuw",
        "ui/tenants_ui.py::tenant_opslaan",
    }
)


# Writes to another domain's mapped classes as of 29 September 2026 (#1254), one key
# per function and class written: membership → mdm 22, audit → activities/mdm/
# membership/payment 13 (the history snapshots), mdm → auth 2, mdm → membership 1,
# media → chatbot 1, payment → membership 1. Phase 3 moves the household writes to
# mdm (B2.5); phase 2 turns `_activate_membership` into a membership handler.
FOREIGN_WRITES: frozenset[str] = frozenset(
    {
        "domains/audit/service.py::snapshot_activity → activities.ActivityHistory",
        "domains/audit/service.py::snapshot_activity_date → activities.ActivityDateHistory",
        "domains/audit/service.py::snapshot_address → mdm.AddressHistory",
        "domains/audit/service.py::snapshot_component → activities.ComponentHistory",
        "domains/audit/service.py::snapshot_contact_detail → mdm.ContactDetailHistory",
        "domains/audit/service.py::snapshot_member → mdm.MemberHistory",
        "domains/audit/service.py::snapshot_member_person → mdm.MemberPersonHistory",
        "domains/audit/service.py::snapshot_membership → membership.MembershipHistory",
        "domains/audit/service.py::snapshot_payment_record → payment.PaymentRecordHistory",
        "domains/audit/service.py::snapshot_person → mdm.PersonHistory",
        "domains/audit/service.py::snapshot_product → activities.ProductHistory",
        "domains/audit/service.py::snapshot_registration_item → activities.RegistrationItemHistory",
        "domains/mdm/import_service.py::_create_admin_users → auth.User",
        "domains/mdm/import_service.py::_create_admin_users → auth.UserRole",
        "domains/mdm/import_service.py::_ensure_membership → membership.Membership",
        "domains/media/extraction.py::update_media_extracted_text → chatbot.ChatbotInfo",
        "domains/membership/household_service.py::add_person_to_family → mdm.MemberPerson",
        "domains/membership/household_service.py::add_person_to_family → mdm.Person",
        "domains/membership/household_service.py::assign_board_member → mdm.Member",
        "domains/membership/household_service.py::create_family_with_members → mdm.Address",
        "domains/membership/household_service.py::create_family_with_members → mdm.Member",
        "domains/membership/household_service.py::create_family_with_members → mdm.MemberPerson",
        "domains/membership/household_service.py::create_family_with_members → mdm.Person",
        "domains/membership/household_service.py::delete_family → mdm.Member",
        "domains/membership/household_service.py::update_person → mdm.Person",
        "domains/membership/household_service.py::update_person_address → mdm.Address",
        "domains/membership/service.py::set_relation_type → mdm.MemberPerson",
    }
)


# Functions that write after they committed (§B9.3 (b)), 29 September 2026. The one
# the change request names: phase 1 makes `delete_registration` commit once, at the end.
WRITE_AFTER_COMMIT: frozenset[str] = frozenset({})


# Functions another domain's service, handler or tool calls through `api.py` and that
# commit (§B9.3 (c)), 29 September 2026, followed three calls deep including late
# imports. A router or screen calling another domain's
# service is not here: that service is the request's door. Mail's `_log_email` is
# the phase 4 job enqueuer (§B4.1); media and designstudio meet in phase 4.
COMMIT_BEHIND_API: frozenset[str] = frozenset(
    {
        "forms.api.submit_bericht",
    }
)


# Calls into another domain's command outside a `@subscribe` function (§B4.9, R12),
# 29 September 2026, one key per calling function and command. A command is derived
# from the code: an `api.py` export that writes or commits (master CLI, 29 Sep). The
# audit snapshots (84 of these) become events or move with their writers; the rest
# are the couplings B4.9 names — mail, payment, workflow, media — and phase 3's
# household moves.
#
# Two entries were ADDED after the freeze, by decision (Koen, 29 September 2026): the
# synchronous commands of `activities` into `forms` (CR-14 §B4.2, §B4.7). When a call
# is an event, a port or a read — and when a port gets built instead of an entry
# here — is one rule, written once: `docs/architecture.md` §3.2.1.
COMMAND_CALLS: frozenset[str] = frozenset(
    {
        "domains/activities/service.py::_copy_components → forms.api.copy_form",  # #1397: synchronous copy, returned id; Koen 1 Oct 2026; the port follows in its own CR
        "domains/newsletter/service.py::_pictures → media.api.activity_image_path",  # #1368, measured 30 Sep 2026: the walk now sees a flush; media caches a PDF poster's rendering (poster.thumbnail + db.flush) — a read with a cache write, not a coupling to move
        "domains/activities/fiche.py::_store_files → media.api.drop_activity_poster",  # #1559: the attachments of the one save
        "domains/activities/fiche.py::_store_files → media.api.drop_component_info",  # #1559: the attachments of the one save
        "domains/activities/fiche.py::_store_files → media.api.store_activity_poster",  # #1559: the attachments of the one save
        "domains/activities/fiche.py::_store_files → media.api.store_component_info",  # #1559: the attachments of the one save
        "domains/activities/router.py::create_registration → payment.api.create_payment_record",
        "domains/activities/service.py::insert_date → audit.api.snapshot_activity_date",  # #1559: moved with the core out of `add_activity_date`
        "domains/activities/service.py::_insert_component → audit.api.snapshot_component",
        "domains/activities/service.py::_insert_product → audit.api.snapshot_product",
        "domains/activities/service.py::_add_activity → audit.api.snapshot_activity",
        "domains/activities/service.py::_add_activity → audit.api.snapshot_activity_date",
        "domains/activities/service.py::delete_activity → audit.api.snapshot_activity",
        "domains/activities/service.py::delete_activity → audit.api.snapshot_activity_date",
        "domains/activities/service.py::delete_activity → audit.api.snapshot_component",
        "domains/activities/service.py::delete_activity → audit.api.snapshot_product",
        "domains/activities/service.py::remove_date → audit.api.snapshot_activity_date",  # #1559: moved with the core out of `delete_activity_date`
        "domains/activities/service.py::remove_component → audit.api.snapshot_component",  # #1559: moved with the core out of `delete_component`
        "domains/activities/service.py::remove_component → audit.api.snapshot_product",  # #1559: moved with the core out of `delete_component`
        "domains/activities/service.py::remove_product → audit.api.snapshot_product",  # #1559: moved with the core out of `delete_product`
        "domains/activities/service.py::delete_registration → audit.api.snapshot_registration_item",
        "domains/activities/service.py::register → audit.api.snapshot_registration_item",
        "domains/activities/service.py::apply_activity_update → audit.api.snapshot_activity",  # #1559: moved with the core out of `update_activity`
        "domains/activities/service.py::apply_date_update → audit.api.snapshot_activity_date",  # #1559: moved with the core out of `update_activity_date`
        "domains/activities/service.py::apply_component_update → audit.api.snapshot_component",  # #1559: moved with the core out of `update_component`
        "domains/activities/service.py::update_order_line → audit.api.snapshot_registration_item",
        "domains/activities/service.py::set_order_quantities → audit.api.snapshot_registration_item",  # #1494: same coupling as add/update/delete_order_line which it bundles, in one transaction; the port of all four is #1502 (Koen, 2 October 2026)
        "domains/activities/service.py::apply_product_update → audit.api.snapshot_product",  # #1559: moved with the core out of `update_product`
        "domains/auth/login.py::start_login → mail.api.send_magic_link",
        "domains/auth/login.py::start_login → mail.api.send_member_contact_board_notice",
        "domains/chatbot/tools.py::submit_idea → forms.api.submit_bericht",
        "domains/designstudio/handlers.py::generate_image → media.api.store_uploads",
        "domains/designstudio/service.py::_prune_versions → media.api.remove_media",
        "domains/designstudio/service.py::_store_render → media.api.add_document",
        "domains/designstudio/service.py::add_design_image → media.api.store_uploads",
        "domains/designstudio/service.py::publish → media.api.store_activity_poster",
        "domains/designstudio/service.py::remove_edited_svg → media.api.remove_media",
        "domains/designstudio/service.py::upload_edited_svg → media.api.add_document",
        "domains/designstudio/service.py::upload_edited_svg → media.api.remove_media",
        "domains/forms/api.py::submit_bericht → mail.api.send_form_confirmation",
        "domains/forms/service.py::submit_form → mail.api.send_form_confirmation",
        "domains/mdm/household_service.py::_upsert_contact → audit.api.snapshot_contact_detail",
        "domains/mdm/household_service.py::insert_household_person → audit.api.snapshot_contact_detail",
        "domains/mdm/household_service.py::insert_household_person → audit.api.snapshot_member_person",
        "domains/mdm/household_service.py::insert_household_person → audit.api.snapshot_person",
        "domains/mdm/household_service.py::detach_household_person → audit.api.snapshot_member_person",
        "domains/mdm/household_service.py::apply_address → audit.api.snapshot_address",
        "domains/mdm/household_service.py::apply_person_fields → audit.api.snapshot_person",
        "domains/mdm/import_service.py::_create_person → audit.api.snapshot_member_person",
        "domains/mdm/import_service.py::_create_person → audit.api.snapshot_person",
        "domains/mdm/import_service.py::_ensure_membership → audit.api.snapshot_membership",
        "domains/mdm/import_service.py::_link_board_members → audit.api.snapshot_member",
        "domains/mdm/import_service.py::_revive_soft_deleted → audit.api.snapshot_member",
        "domains/mdm/import_service.py::_revive_soft_deleted → audit.api.snapshot_person",
        "domains/mdm/import_service.py::_sync_address → audit.api.snapshot_address",
        "domains/mdm/import_service.py::_sync_family → audit.api.snapshot_member_person",
        "domains/mdm/import_service.py::_sync_family → audit.api.snapshot_person",
        "domains/mdm/import_service.py::upsert_families → audit.api.snapshot_member",
        "domains/mdm/service.py::add_email_address → audit.api.snapshot_contact_detail",
        "domains/mdm/service.py::write_email_rows → audit.api.snapshot_contact_detail",
        "domains/mdm/service.py::promote_email_row → audit.api.snapshot_contact_detail",
        "domains/mdm/service.py::remove_email_address → audit.api.snapshot_contact_detail",
        "domains/mdm/service.py::upsert_primary_contact → audit.api.snapshot_contact_detail",
        "domains/mdm/ui.py::adres_opslaan → membership.api.update_family_address",
        "domains/mdm/ui.py::bestuurslid_zetten → membership.api.assign_board_member",
        "domains/mdm/ui.py::gezin_aanmaken → membership.api.create_family_by_admin",
        "domains/mdm/ui.py::gezin_verwijderen → membership.api.delete_family",
        "domains/mdm/ui.py::lidmaatschap_toevoegen → membership.api.create_membership_for_family",
        "domains/mdm/ui.py::lidmaatschap_verwijderen → membership.api.delete_membership",
        "domains/mdm/ui.py::persoon_opslaan → membership.api.set_relation_type",
        "domains/mdm/ui.py::persoon_opslaan → membership.api.update_person",
        "domains/mdm/ui.py::persoon_opslaan → membership.api.update_person_contacts",
        "domains/mdm/ui.py::persoon_toevoegen → membership.api.add_person_to_family",
        "domains/meetings/admin_ui.py::circle_add → mdm.api.add_to_circle",
        "domains/meetings/admin_ui.py::circle_end → mdm.api.end_circle_relation",
        "domains/meetings/admin_ui.py::circle_new_person → mdm.api.create_person_for_circle",
        "domains/meetings/service.py::send_meeting_mail → mail.api.send_with_attachments",
        "domains/membership/portal_service.py::renew_membership → audit.api.snapshot_membership",
        "domains/membership/portal_service.py::renew_membership → payment.api.create_payment_record",
        "domains/membership/household_service.py::_reconcile_geschrapt_lidmaatschap → payment.api.reconcile_charges",
        "domains/membership/household_service.py::add_person_to_family → audit.api.snapshot_contact_detail",
        "domains/membership/household_service.py::add_person_to_family → audit.api.snapshot_member_person",
        "domains/membership/household_service.py::add_person_to_family → audit.api.snapshot_person",
        "domains/membership/household_service.py::assign_board_member → audit.api.snapshot_member",
        "domains/membership/household_service.py::create_family_with_members → audit.api.snapshot_address",
        "domains/membership/household_service.py::create_family_with_members → audit.api.snapshot_contact_detail",
        "domains/membership/household_service.py::create_family_with_members → audit.api.snapshot_member",
        "domains/membership/household_service.py::create_family_with_members → audit.api.snapshot_member_person",
        "domains/membership/household_service.py::create_family_with_members → audit.api.snapshot_membership",
        "domains/membership/household_service.py::create_family_with_members → audit.api.snapshot_person",
        "domains/membership/household_service.py::create_membership_for_family → audit.api.snapshot_membership",
        "domains/membership/household_service.py::delete_family → audit.api.snapshot_address",
        "domains/membership/household_service.py::delete_family → audit.api.snapshot_contact_detail",
        "domains/membership/household_service.py::delete_family → audit.api.snapshot_member",
        "domains/membership/household_service.py::delete_family → audit.api.snapshot_member_person",
        "domains/membership/household_service.py::delete_family → audit.api.snapshot_membership",
        "domains/membership/household_service.py::delete_family → audit.api.snapshot_person",
        "domains/membership/household_service.py::delete_membership → audit.api.snapshot_membership",
        # CR-22 S7 (#1712): the delete of a person moved to master data — one
        # rule, `mdm.service.delete_person` — and its history calls with it;
        # membership's door calls that rule. Four entries left, four came.
        "domains/mdm/ui.py::persoon_verwijderen → membership.api.delete_person",
        "domains/mdm/service.py::delete_person → audit.api.snapshot_address",
        "domains/mdm/service.py::delete_person → audit.api.snapshot_contact_detail",
        "domains/mdm/service.py::delete_person → audit.api.snapshot_person",
        "domains/membership/household_service.py::delete_person → mdm.api.delete_person",
        "domains/membership/household_service.py::update_person → audit.api.snapshot_person",
        "domains/membership/household_service.py::update_person_address → audit.api.snapshot_address",
        "domains/membership/household_service.py::update_person_contacts._upsert_contact → mdm.api.upsert_primary_contact",
        "domains/membership/signup_service.py::register_family → payment.api.create_payment_record",
        "domains/membership/service.py::activate_after_payment → audit.api.snapshot_membership",
        "domains/newsletter/service.py::add_attachment → media.api.add_document",
        "domains/newsletter/service.py::send_batch → mail.api.send_campaign_mail",
        "domains/newsletter/service.py::send_test → mail.api.send_campaign_mail",
        "domains/newsletter/service.py::subscribe_public → mail.api.send_newsletter_confirmation",
        "domains/payment/service.py::confirm_manual_payment → audit.api.snapshot_payment_record",
        "domains/payment/service.py::create_payment_record → audit.api.snapshot_payment_record",
        "domains/payment/service.py::create_refund → audit.api.snapshot_payment_record",
        "domains/payment/service.py::delete_payment_record → audit.api.snapshot_payment_record",
        "domains/payment/service.py::edit_payment_record → audit.api.snapshot_payment_record",
        "domains/payment/service.py::handle_gateway_update → audit.api.snapshot_payment_record",
        "domains/payment/service.py::reconcile_charges → audit.api.snapshot_payment_record",
        "domains/payment/service.py::set_payment_status → audit.api.snapshot_payment_record",
        "domains/payment/service.py::void_payment_record → audit.api.snapshot_payment_record",
    }
)


# Refusals decided at the door (§B9.3, *no rule in a router*), 29 September 2026, with
# a reason per entry, as the change request asks: a `rule` moves to its entity or
# service in the phase named; a `door` entry is the request's shape (a file's size or
# type, an empty upload, a parameter) and is the doorman's own — the phase that
# sweeps its domain decides whether the gate learns to except it or it stays named.
# Keys are `file::function::condition` — the condition text, not a line number.
RULE_IN_ROUTER: dict[str, str] = {
    "domains/auth/router.py::create_api_key::db.query(ApiKey).filter(ApiKey.name == name).first()": "rule: API key names are unique (ApiKey, with a UNIQUE constraint) — phase 4",
    "domains/auth/router.py::create_api_key::not name": "rule: an API key has a name (ApiKey) — phase 4",
    "domains/cms/admin_ui.py::pagina_aanmaken::not title.strip() or not slug.strip()": "rule: a page has a title and a slug (CmsPage) — phase 4",
}


# Writes to a mapped class in a router, UI module or `@subscribe` handler (§B9.3,
# *one entrance rule* (b)), 29 September 2026. The household router (phase 3) and the
# registration router (phase 1) are the ones the change request names.
WRITE_OUTSIDE_SERVICE: frozenset[str] = frozenset(
    {
        "domains/auth/router.py::create_api_key → auth.ApiKey",
        "domains/auth/router.py::revoke_api_key → auth.ApiKey",
        "domains/auth/router.py::verify_login → auth.LoginToken",
    }
)


# Empty since CR-13 phase 4: the two bulk UPDATEs (the living login tokens, the merge
# chain) write through the objects now.
NON_ORM_WRITES: frozenset[str] = frozenset()


# Empty since CR-13 phase 4: the activity list asks the service whether a date has
# passed (`date_passed`/`date_upcoming`), the comparison `registration_state` makes.
DERIVED_ELSEWHERE: frozenset[str] = frozenset()


# Promises a template makes that walk to a column nothing keeps (§B9.3, *promise
# kept*), 29 September 2026: none. Of 50 promises, 31 walk to a kept column or a
# schema constraint; the other 19 cannot be walked and are below. Empty, so any new
# unkept promise is red.
PROMISE_NOT_KEPT: frozenset[str] = frozenset()


# Promises the walk cannot follow from template to column, each with the step where
# it stops — the reason the change request asks for (§B10: the spike counted 21 on
# 27 September; the gate's 19 bind). A partial without its own <form> (the
# registration fields among them) is the largest group; phase 1 walks the
# registration form through its facade.
PROMISE_UNWALKABLE: dict[str, str] = {
    "domains/chatbot/templates/_raakje_controls.html::vraag::required": "no form target (built in JS, by a macro, or GET)",
    "domains/designstudio/templates/admin_ontwerp.html::main_focus_x::min": "route `design_save` does not read `main_focus_x` by name",
    "domains/designstudio/templates/admin_ontwerp.html::main_focus_y::min": "route `design_save` does not read `main_focus_y` by name",
    "domains/forms/templates/_berichten_form.html::bericht::required": "no column named `bericht`",
    "domains/forms/templates/_berichten_form.html::naam::required": "no column named `naam`",
    "domains/forms/templates/_fb_builder.html::label::required": "no writing route for /admin/formulieren/{}{% if f %}/velden/{}{% else %}/velden{% endif %}",
    "domains/forms/templates/_fb_builder.html::required::required": "no writing route for /admin/formulieren/{}{% if f %}/velden/{}{% else %}/velden{% endif %}",
    "domains/mdm/templates/_leden_adres_velden.html::house_number::required": "no form target (built in JS, by a macro, or GET)",
    "domains/mdm/templates/_leden_adres_velden.html::street::required": "no form target (built in JS, by a macro, or GET)",
    "domains/mdm/templates/leden_import.html::file::required": "no column named `file`",
    "domains/media/templates/admin_media_nieuw.html::files::required": "no column named `files`",
    "domains/meetings/templates/admin_vergadering_nieuw.html::meeting_date::required": "no writing route for {}",
    "domains/newsletter/templates/_nb_instellingen.html::daily_cap::min": "no column named `daily_cap`",
    "domains/newsletter/templates/_nb_publiek.html::email::required": "no writing route for {}",
    "ui/templates/design_system.html::naam::required": "no form target (built in JS, by a macro, or GET)",
}
