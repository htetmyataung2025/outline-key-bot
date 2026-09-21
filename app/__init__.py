"""Outline Key Bot application package.

Phase 1/2 layout (handlers + routes still live in root ``index.py`` and
will move to ``app/handlers/`` + ``app/routes.py`` in Phase 3)::

    app/
      config.py      env-based settings + PLANS catalog
      extensions.py  Flask app + TeleBot singletons
      constants.py   (reserved)
      texts.py       user-facing message builders
      keyboards.py   reply/inline keyboard factories
      utils.py       pure helpers
      storage/       paths + Upstash Redis REST client
      services/      billing, ocr, orders, registry, outline, reports,
                     notifier, states
"""
