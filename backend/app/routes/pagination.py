from werkzeug.exceptions import BadRequest


def pagination_args(args):
    if set(args) - {"page", "per_page"} or any(len(args.getlist(key)) != 1 for key in args):
        raise BadRequest("Parametrii permisi sunt page si per_page, o singura data fiecare.")
    try:
        page, per_page = int(args.get("page", "1")), int(args.get("per_page", "20"))
    except ValueError:
        raise BadRequest("Paginarea trebuie sa contina numere intregi.") from None
    if not 1 <= page <= 1000000 or not 1 <= per_page <= 100:
        raise BadRequest("Paginare invalida: page 1-1000000, per_page 1-100.")
    return {"page": page, "per_page": per_page}
