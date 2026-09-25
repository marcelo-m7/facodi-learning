from .services.curriculum_bootstrap import ensure_lesti_2026_27


def post_init_hook(env):
    ensure_lesti_2026_27(env)
    env["website"].search([]).action_facodi_enable_publication_review()
