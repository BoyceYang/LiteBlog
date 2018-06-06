from datetime import datetime
from flask import render_template, session, redirect, url_for, request, abort, current_app, flash,make_response
from flask_login import current_user
from . import main
from .forms import PostForm, EditProfileForm,EditProfileAdminForm, CommentForm
from .. import db, photos
from ..models import User, Role, Post, Comment, Count
from ..email import send_email
from ..decorators import admin_required, permission_required
from ..models import Permission
from flask_login import login_required


@main.route("/", methods=["GET", "POST"])
def index():
    form = PostForm()
    page = request.args.get('page', 1, type=int)
    article_type = request.cookies.get('article_type', '')
    if article_type != '':
        query = Post.query.filter_by(article_type=article_type)
    else:
        query = Post.query
    pagination = query.order_by(Post.timestamp.desc()).paginate(page,
                                                                per_page=current_app.config['FLASKY_POSTS_PER_PAGE'],
                                                                error_out=False)
    posts = pagination.items
    try:
        count = Count.query.filter_by(post_id=0).first()
    except:
        count = Count(post_id=0, cnt=0)
    count.cnt += 1
    db.session.add(count)
    db.session.commit()
    return render_template('index.html', form=form, posts=posts, article_type=article_type, pagination=pagination,
                           cnt=count.cnt)


@main.route('/admin', methods=["GET", "POST"])
@login_required
@admin_required
def for_admins_only():
    return "For administrators!"


@main.route('/moderator')
@login_required
@permission_required(Permission.MODERATE_COMMENTS)
def for_moderators_only():
    return "For comment moderators!"


@main.route("/user/<username>",methods=["GET", "POST"])
def user(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        abort(404)
    page = request.args.get("page", 1, type=int)
    pagination = user.posts.order_by(Post.timestamp.desc()).paginate(page, per_page=current_app.config['FLASKY_POSTS_PER_PAGE'],error_out=False)
    posts = pagination.items
    return render_template("user.html", user=user, posts=posts,pagination=pagination)  


@main.route("/editProfile", methods=["GET", "POST"])
@login_required
def edit_user():
    form = EditProfileForm()
    if form.validate_on_submit():
        current_user.location = form.location.data
        current_user.about_me = form.about_me.data
        if form.photo.data:
            current_user.image_filename = photos.save(form.photo.data,name="user/" + current_user.username + ".")
            current_user.image_url = photos.url(current_user.image_filename)
        db.session.add(current_user)
        return redirect(url_for("main.user", username=current_user.username))
    form.location.data = current_user.location
    form.about_me.data = current_user.about_me
    return render_template("editProfile.html", form=form, image_url=current_user.image_url)


@main.route('/edit-profile/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_profile_admin(id):
    user = User.query.get_or_404(id)
    form = EditProfileAdminForm(user=user)
    if form.validate_on_submit():
        user.email = form.email.data
        user.username = form.username.data
        user.confirmed = form.confirmed.data
        user.role = Role.query.get(form.role.data)
        user.location = form.location.data
        user.about_me = form.about_me.data
        if form.photo.data:
            user.image_filename = photos.save(form.photo.data, name="user/" + user.username+".")
            user.image_url = photos.url(user.image_filename)
        db.session.add(user)
        return redirect(url_for('.user', username=user.username))
    form.email.data = user.email
    form.username.data = user.username
    form.confirmed.data = user.confirmed
    form.role.data = user.role_id
    form.location.data = user.location
    form.about_me.data = user.about_me
    return render_template('editProfile.html', form=form, user=user,image_url=user.image_url)


@main.route("/post/<int:id>", methods=['GET', 'POST'])
def post(id):
    show_more = False
    post = Post.query.get_or_404(id)
    form = CommentForm()
    if current_user.can(Permission.COMMENT) and form.validate_on_submit():
        comment = Comment(body=form.body.data,author=current_user._get_current_object(),post=post)
        db.session.add(comment)
        return redirect(url_for('main.post', id=id))
    page = request.args.get('page', 1, type=int)
    pagination = Comment.query.filter_by(post_id=id,disable=False).order_by(Comment.timestamp.desc()).paginate(page, per_page=current_app.config['FLASKY_POSTS_PER_PAGE'], error_out=False)
    comments = pagination.items
    try:
        count = Count.query.filter_by(post_id=id).first()
    except:
        count = Count(post_id=id, cnt=0)
    count.cnt += 1
    db.session.add(count)
    db.session.commit()
    return render_template("post.html", form=form, posts=[post], comments=comments, pagination=pagination,
                           show_more=show_more, post_cnt=count.cnt)


@main.route("/createPost", methods=["GET", "POST"])
@login_required
def create_post():
    form = PostForm()
    if current_user.can(Permission.WRITE_ARTICLES) and form.validate_on_submit():
        if len(form.title.data.split('|')) > 1:
            article_type = form.title.data.split('|')[0]
        else:
            article_type = 'python'
        post = Post(title=form.title.data, article_type=article_type, body=form.body.data,
                    author=current_user._get_current_object())
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('main.post', id=post.id))
    return render_template("editPost.html", form=form, createPostFlag=True)


@main.route("/editPost/<int:id>", methods=['GET', 'POST'])
@login_required
def edit_post(id):
    post = Post.query.get_or_404(id)
    if current_user != post.author and not current_user.can(Permission.ADMINISTER):
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.body = form.body.data
        post.title = form.title.data
        if len(form.title.data.split('|')) > 1:
            post.article_type = form.title.data.split('|')[0]
        else:
            post.article_type = 'python'
        db.session.add(post)
        return redirect(url_for("main.post", id=post.id))
    form.body.data = post.body
    form.title.data = post.title
    return render_template("editPost.html", form=form)


@main.route("/delPost/<int:id>", methods=['GET', 'POST'])
@login_required
def del_post(id):
    post = Post.query.get_or_404(id)
    if current_user != post.author and not current_user.can(Permission.ADMINISTER):
        abort(403)
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('main.index'))


@main.route('/follow/<username>')
@login_required
@permission_required(Permission.FOLLOW)
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('main.index'))
    if current_user.is_following(user):
        flash('You are already following this user.')
        return redirect(url_for('main.user', username=username))
    current_user.follow(user)
    return redirect(url_for('main.user', username=username))


@main.route('/unfollow/<username>')
@login_required
@permission_required(Permission.FOLLOW)
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    if not current_user.is_following(user):
        flash('You are not following this user.')
        return redirect(url_for('.user', username=username))
    current_user.unfollow(user)
    return redirect(url_for('.user', username=username))


@main.route('/followers/<username>')
def followers(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    pagination = user.followers.paginate(
        page, per_page=current_app.config['FLASKY_FOLLOWERS_PER_PAGE'],
        error_out=False)
    follows = [{'user': item.follower, 'timestamp': item.timestamp}
               for item in pagination.items]
    return render_template('followers.html', user=user, title="Followers of",
                           endpoint='.followers', pagination=pagination,
                           follows=follows)


@main.route('/followed-by/<username>')
def followed_by(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    pagination = user.followed.paginate(
        page, per_page=current_app.config['FLASKY_FOLLOWERS_PER_PAGE'],
        error_out=False)
    follows = [{'user': item.followed, 'timestamp': item.timestamp}
               for item in pagination.items]
    return render_template('followers.html', user=user, title="Followed by",
                           endpoint='.followed_by', pagination=pagination,
                           follows=follows)


@main.route('/all')
def show_all():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('article_type', '', max_age=30*24*60*60)
    return resp


@main.route('/python')
def show_python():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('article_type', 'python', max_age=30*24*60*60)
    return resp


@main.route('/golang')
def show_golang():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('article_type', 'golang', max_age=30*24*60*60)
    return resp


@main.route('/nodejs')
def show_nodejs():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('article_type', 'nodejs', max_age=30*24*60*60)
    return resp


@main.route('/bk')
def show_bk():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('article_type', 'bk', max_age=30*24*60*60)
    return resp


@main.route('/cloud')
def show_cloud():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('article_type', 'cloud', max_age=30*24*60*60)
    return resp


@main.route('/deploy')
def show_deploy():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('article_type', 'deploy', max_age=30*24*60*60)
    return resp


@main.route('/other')
def show_other():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('article_type', 'other', max_age=30*24*60*60)
    return resp


@main.route("/moderate-comments", methods=["GET", "POST"])
@permission_required(Permission.MODERATE_COMMENTS)
@login_required
def moderate_comments():
    page = request.args.get('page', 1, type=int)
    pagination = Comment.query.order_by(Comment.timestamp.desc())\
        .paginate(page, per_page=current_app.config['FLASKY_POSTS_PER_PAGE'], error_out=False)
    comments = pagination.items
    return render_template('comments.html', pagination=pagination,comments=comments)


@main.route("/disable-comment/<int:id>", methods=["GET","POST"])
@permission_required(Permission.MODERATE_COMMENTS)
@login_required
def disable_comment(id):
    comment = Comment.query.get_or_404(id)
    comment.disable = True
    db.session.add(comment)
    return redirect(url_for("main.moderate_comments", page=request.args.get('page', 1, type=int)))


@main.route("/enable-comment/<int:id>", methods=["GET", "POST"])
@permission_required(Permission.MODERATE_COMMENTS)
@login_required
def enable_comment(id):
    comment = Comment.query.get_or_404(id)
    comment.disable = False
    db.session.add(comment)
    return redirect(url_for("main.moderate_comments", page=request.args.get('page', 1, type=int)))


@main.route("/del-comment/<int:id>", methods=["GET", "POST"])
@permission_required(Permission.MODERATE_COMMENTS)
@login_required
def del_comment(id):
    comment = Comment.query.get_or_404(id)
    db.session.delete(comment)
    db.session.commit()
    return redirect(url_for("main.moderate_comments", page=request.args.get('page', 1, type=int)))

